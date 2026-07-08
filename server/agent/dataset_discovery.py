"""
Ontology-grounded dataset discovery pipeline for multiple repositories.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_access_discovery import enrich_candidates_with_access
from domain.dataset_context_export import export_dataset_search_agent_context
from domain.dataset_repository_registry import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    IMMPORT_REPOSITORY,
    any_load_more_enabled,
    fetch_more_repository_records,
    fetch_repository_records,
    filter_repositories_for_interpreted_query,
    get_repository_spec,
    infer_record_repository,
    is_repository_tool_enabled,
    pick_load_more_cursor,
    repository_priority_map,
    repository_supports_load_more,
    resolve_repository_for_load_more,
    supported_repositories,
)
from domain.dataset_search import (
    DatasetCandidate,
    DatasetSearchCursor,
    DatasetSearchResult,
    InterpretedQuery,
)
from domain.facet_search_strategies import STRATEGY_PRIORITY
from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from domain.ranking import rank_annotated_candidates

SUPPORTED_REPOSITORIES = supported_repositories()
REPOSITORY_PRIORITY = repository_priority_map()


def _as_repository_list(repository: str | list[str]) -> list[str]:
    if isinstance(repository, str):
        return [repository]
    return list(repository)


def canonical_dataset_key(accession: str) -> str:
    """Normalize accessions so GEO GSE* and GXA E-GEOD-* dedupe to the same study."""
    acc = accession.strip().upper()
    if acc.startswith("E-GEOD-"):
        return f"GSE{acc[len('E-GEOD-'):]}"
    return acc


def _record_canonical_key(record: dict) -> str:
    return canonical_dataset_key(str(record.get("accession") or ""))


def _record_strategy_priority(record: dict) -> int:
    strategy = record.get("_retrieval_strategy") or ""
    return STRATEGY_PRIORITY.get(strategy, 99)


def _infer_record_repository(record: dict) -> str:
    return infer_record_repository(record)


def merge_repository_search_results(search_results: list[dict]) -> dict:
    """Merge multi-repository search payloads, deduplicating overlapping studies."""
    if not search_results:
        raise ValueError("No search results to merge")
    if len(search_results) == 1:
        return search_results[0]

    merged_records: dict[str, dict] = {}
    record_rank: dict[str, tuple[int, int]] = {}

    for result in search_results:
        repository = result.get("repository", "")
        repo_priority = REPOSITORY_PRIORITY.get(repository, 99)
        for record in result.get("records", []):
            key = _record_canonical_key(record)
            if not key:
                continue
            rank = (repo_priority, _record_strategy_priority(record))
            existing_rank = record_rank.get(key)
            if existing_rank is None or rank < existing_rank:
                merged_records[key] = {**record, "_source_repository": repository}
                record_rank[key] = rank

    repositories = [result.get("repository") for result in search_results if result.get("repository")]
    sources: list[str] = []
    for result in search_results:
        source = result.get("source")
        if source and source not in sources:
            sources.append(source)

    search_strategies: list[dict] = []
    for result in search_results:
        repository = result.get("repository", "")
        for strategy in result.get("search_strategies", []):
            search_strategies.append({**strategy, "repository": repository})

    return {
        "records": list(merged_records.values()),
        "total_found": sum(result.get("total_found", 0) for result in search_results),
        "primary_total_found": sum(
            result.get("primary_total_found") or 0 for result in search_results
        )
        or None,
        "max_results": max(result.get("max_results") or 0 for result in search_results) or None,
        "repository": " + ".join(repositories),
        "source": ", ".join(sources),
        "search_term": search_results[0].get("search_term"),
        "search_strategies": search_strategies,
        "has_more": any(result.get("has_more") for result in search_results),
        "load_more_cursor": pick_load_more_cursor(search_results),
        "repositories_searched": repositories,
    }


def interpret_query(query: str) -> InterpretedQuery:
    """Step 1: extract structured facets from the user query."""
    return interpret_dataset_query(query)


def interpret_query_pipeline(query: str) -> tuple[InterpretedQuery, dict[str, Any] | None]:
    """Step 1 (+ optional LLM): rules first, then validated LLM facet fallback."""
    from domain.llm_query_interpretation import maybe_llm_interpret_query

    interpreted = interpret_dataset_query(query)
    interpreted, llm_trace = maybe_llm_interpret_query(query, interpreted)
    return interpreted, llm_trace


def ground_query(interpreted: InterpretedQuery):
    """Step 2: provider-based ontology grounding of requested facets."""
    return enrich_concept_mappings(ground_interpreted_query(interpreted))


def _species_from_interpreted(interpreted: InterpretedQuery | None) -> str | None:
    if interpreted and interpreted.organism == "human":
        return "Homo sapiens"
    if interpreted and interpreted.organism:
        return interpreted.organism
    return None


def search_repository(
    repository: str,
    concept_mappings,
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    include_text_broad: bool = True,
) -> dict:
    """Step 3: multi-strategy repository search using grounded labels and synonyms."""
    return fetch_repository_records(
        repository,
        concept_mappings,
        max_results=max_results,
        query=query,
        interpreted_query=interpreted_query,
        species=_species_from_interpreted(interpreted_query),
        include_text_broad=include_text_broad,
    )


def search_repositories(
    repositories: list[str],
    concept_mappings,
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    include_text_broad: bool = True,
) -> dict:
    """Step 3 (multi): search each enabled repository and merge with deduplication."""
    unsupported = [repo for repo in repositories if repo not in SUPPORTED_REPOSITORIES]
    if unsupported:
        raise ValueError(f"Unsupported dataset repositories: {', '.join(unsupported)}")

    search_results = [
        search_repository(
            repository,
            concept_mappings,
            max_results=resolve_max_results(repository, max_results),
            query=query,
            interpreted_query=interpreted_query,
            include_text_broad=include_text_broad,
        )
        for repository in repositories
    ]
    return merge_repository_search_results(search_results)


def normalize_records(repository: str, raw_records: list[dict]) -> list[DatasetCandidate]:
    """Step 4: repository record normalization into shared DatasetCandidate models."""
    return get_repository_spec(repository).normalize_records(raw_records)


def normalize_merged_records(raw_records: list[dict]) -> list[DatasetCandidate]:
    """Step 4 (multi): normalize records from multiple repositories."""
    by_repository: dict[str, list[dict]] = defaultdict(list)
    for record in raw_records:
        by_repository[_infer_record_repository(record)].append(record)

    candidates: list[DatasetCandidate] = []
    for repository, repo_records in by_repository.items():
        candidates.extend(normalize_records(repository, repo_records))
    return candidates


def annotate_evidence(candidates, concept_mappings):
    """Step 5: annotate returned records with evidence snippets and warnings."""
    return annotate_dataset_candidates(candidates, concept_mappings)


def rank_results(candidates, concept_mappings):
    """Step 6: rank annotated candidates by evidence coverage."""
    return rank_annotated_candidates(candidates, concept_mappings)


def discover_access(candidates: list[DatasetCandidate]) -> list[DatasetCandidate]:
    """Step 7: discover repository access links and summaries for ranked candidates."""
    return enrich_candidates_with_access(candidates)


def resolve_max_results(repository: str, max_results: int | None = None) -> int:
    return get_repository_spec(repository).resolve_max_results(max_results)


def _build_dataset_search_result(
    *,
    query: str,
    interpreted: InterpretedQuery,
    concept_mappings,
    ranked: list[DatasetCandidate],
    search_result: dict,
    repository: str,
) -> DatasetSearchResult:
    cursor_payload = search_result.get("load_more_cursor")
    cursor = (
        DatasetSearchCursor.model_validate(cursor_payload)
        if cursor_payload is not None
        else None
    )
    spec = get_repository_spec(repository) if repository in SUPPORTED_REPOSITORIES else None
    default_source = spec.source_display if spec else repository
    return DatasetSearchResult(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        candidates=ranked,
        total_found=search_result.get("total_found", len(ranked)),
        primary_total_found=search_result.get("primary_total_found"),
        max_results=search_result.get("max_results"),
        source=search_result.get("source", default_source),
        repository=search_result.get("repository", repository),
        search_term=search_result.get("search_term") or None,
        search_strategies=search_result.get("search_strategies", []),
        has_more=search_result.get("has_more", False),
        retrieved_count=len(ranked),
        retrievable_total=search_result.get("retrievable_total"),
        include_text_broad=search_result.get("include_text_broad"),
        text_broad_total_found=search_result.get("text_broad_total_found"),
        load_more_cursor=cursor,
    )


def run_dataset_discovery(
    query: str,
    *,
    repository: str | list[str] = GEO_REPOSITORY,
    max_results: int | None = None,
) -> DatasetSearchResult:
    """Run the full dataset-discovery pipeline for one or more repositories."""
    repositories = _as_repository_list(repository)
    unsupported = [repo for repo in repositories if repo not in SUPPORTED_REPOSITORIES]
    if unsupported:
        raise ValueError(f"Unsupported dataset repositories: {', '.join(unsupported)}")

    interpreted, _llm_trace = interpret_query_pipeline(query)
    concept_mappings = ground_query(interpreted)
    repositories, skipped_repositories = filter_repositories_for_interpreted_query(
        repositories,
        interpreted,
        query=query,
    )
    if not repositories:
        raise ValueError(
            "No dataset repositories remain for this query after applying assay filters. "
            "Try enabling OmicsDI for metabolomics queries."
        )
    if len(repositories) == 1:
        repo = repositories[0]
        search_result = search_repository(
            repo,
            concept_mappings,
            max_results=resolve_max_results(repo, max_results),
            query=query,
            interpreted_query=interpreted,
        )
        candidates = normalize_records(repo, search_result.get("records", []))
        result_repository = repo
    else:
        search_result = search_repositories(
            repositories,
            concept_mappings,
            max_results=max_results,
            query=query,
            interpreted_query=interpreted,
        )
        candidates = normalize_merged_records(search_result.get("records", []))
        result_repository = search_result.get("repository", " + ".join(repositories))

    if skipped_repositories:
        search_result = {**search_result, "skipped_repositories": skipped_repositories}

    annotated = annotate_evidence(candidates, concept_mappings)
    ranked = rank_results(annotated, concept_mappings)
    ranked = discover_access(ranked)
    return _build_dataset_search_result(
        query=query,
        interpreted=interpreted,
        concept_mappings=concept_mappings,
        ranked=ranked,
        search_result=search_result,
        repository=result_repository,
    )


def load_more_dataset_search(
    cursor: DatasetSearchCursor,
    existing_candidates: list[DatasetCandidate],
) -> DatasetSearchResult:
    """Fetch the next batch for a repository cursor, merge, and re-rank."""
    repository = resolve_repository_for_load_more(cursor, existing_candidates)
    if not repository_supports_load_more(repository):
        raise RuntimeError(f"Load-more is not implemented for {repository}")

    more_result = fetch_more_repository_records(repository, cursor)
    if more_result.get("error") and not more_result.get("records"):
        raise RuntimeError(more_result["error"])

    spec = get_repository_spec(repository)
    new_candidates = normalize_records(repository, more_result.get("records", []))
    new_annotated = annotate_evidence(new_candidates, cursor.concept_mappings)
    merged = list(existing_candidates) + new_annotated
    ranked = rank_results(merged, cursor.concept_mappings)
    ranked = discover_access(ranked)

    cursor_payload = more_result.get("load_more_cursor")
    updated_cursor = (
        DatasetSearchCursor.model_validate(cursor_payload)
        if cursor_payload is not None
        else cursor.model_copy(update={"has_more": more_result.get("has_more", False)})
    )

    search_result = {
        "total_found": cursor.total_found,
        "primary_total_found": cursor.primary_total_found,
        "retrievable_total": more_result.get("retrievable_total"),
        "include_text_broad": more_result.get(
            "include_text_broad",
            cursor.include_text_broad,
        ),
        "text_broad_total_found": more_result.get(
            "text_broad_total_found",
            cursor.text_broad_total_found,
        ),
        "max_results": cursor.max_results,
        "source": more_result.get("source", spec.source_display),
        "repository": more_result.get("repository", repository),
        "search_term": cursor.search_term,
        "search_strategies": [],
        "has_more": more_result.get("has_more", False),
        "load_more_cursor": updated_cursor.model_dump(),
    }
    return _build_dataset_search_result(
        query=cursor.query,
        interpreted=cursor.interpreted_query,
        concept_mappings=cursor.concept_mappings,
        ranked=ranked,
        search_result=search_result,
        repository=repository,
    )


def dataset_search_result_payload(result: DatasetSearchResult) -> dict:
    """Serialize a dataset search result with agent context export."""
    payload = result.model_dump()
    payload["agent_context"] = export_dataset_search_agent_context(result)
    return payload
