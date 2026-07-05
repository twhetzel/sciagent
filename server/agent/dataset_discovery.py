"""
Ontology-grounded dataset discovery pipeline for multiple repositories.
"""

from __future__ import annotations

from collections import defaultdict

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_access_discovery import enrich_candidates_with_access
from domain.dataset_context_export import export_dataset_search_agent_context
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
from tools.expression_atlas import (
    fetch_gxa_repository_records,
    get_expression_atlas_max_results,
    normalize_gxa_records,
)
from tools.geo_dataset_search import (
    fetch_geo_repository_records,
    fetch_more_geo_repository_records,
    get_geo_max_results,
    normalize_geo_records,
)

GEO_REPOSITORY = "GEO"
GXA_REPOSITORY = "Expression Atlas"

SUPPORTED_REPOSITORIES = frozenset({GEO_REPOSITORY, GXA_REPOSITORY})

REPOSITORY_PRIORITY = {
    GEO_REPOSITORY: 0,
    GXA_REPOSITORY: 1,
}


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
    tagged = record.get("_source_repository")
    if tagged in SUPPORTED_REPOSITORIES:
        return tagged
    accession = str(record.get("accession") or "").upper()
    if accession.startswith("GSE"):
        return GEO_REPOSITORY
    if accession.startswith("E-"):
        return GXA_REPOSITORY
    return GEO_REPOSITORY


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

    geo_result = next(
        (result for result in search_results if result.get("repository") == GEO_REPOSITORY),
        None,
    )

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
        "load_more_cursor": geo_result.get("load_more_cursor") if geo_result else None,
        "repositories_searched": repositories,
    }


def interpret_query(query: str) -> InterpretedQuery:
    """Step 1: extract structured facets from the user query."""
    return interpret_dataset_query(query)


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
) -> dict:
    """Step 3: multi-strategy repository search using grounded labels and synonyms."""
    if repository == GEO_REPOSITORY:
        return fetch_geo_repository_records(
            concept_mappings,
            max_results=max_results,
            query=query,
            interpreted_query=(
                interpreted_query.model_dump() if interpreted_query is not None else None
            ),
        )
    if repository == GXA_REPOSITORY:
        return fetch_gxa_repository_records(
            concept_mappings,
            max_results=max_results,
            query=query,
            interpreted_query=interpreted_query,
            species=_species_from_interpreted(interpreted_query),
        )
    raise ValueError(f"Unsupported dataset repository: {repository}")


def search_repositories(
    repositories: list[str],
    concept_mappings,
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
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
        )
        for repository in repositories
    ]
    return merge_repository_search_results(search_results)


def normalize_records(repository: str, raw_records: list[dict]) -> list[DatasetCandidate]:
    """Step 4: repository record normalization into shared DatasetCandidate models."""
    if repository == GEO_REPOSITORY:
        return normalize_geo_records(raw_records)
    if repository == GXA_REPOSITORY:
        return normalize_gxa_records(raw_records)
    raise ValueError(f"Unsupported dataset repository: {repository}")


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
    if repository == GEO_REPOSITORY:
        return get_geo_max_results(max_results)
    if repository == GXA_REPOSITORY:
        return get_expression_atlas_max_results(max_results)
    raise ValueError(f"Unsupported dataset repository: {repository}")


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
    default_source = "NCBI GEO" if repository == GEO_REPOSITORY else "Expression Atlas"
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

    interpreted = interpret_query(query)
    concept_mappings = ground_query(interpreted)
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
    """
    Fetch the next batch for a repository cursor, merge, and re-rank.

    Load-more is currently implemented for GEO only.
    """
    if cursor.concept_mappings:
        repository = existing_candidates[0].repository if existing_candidates else GEO_REPOSITORY
    else:
        repository = GEO_REPOSITORY

    if repository != GEO_REPOSITORY:
        raise RuntimeError(f"Load-more is not yet implemented for {repository}")

    more_result = fetch_more_geo_repository_records(cursor)
    if more_result.get("error") and not more_result.get("records"):
        raise RuntimeError(more_result["error"])

    new_candidates = normalize_records(GEO_REPOSITORY, more_result.get("records", []))
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
        "max_results": cursor.max_results,
        "source": more_result.get("source", "NCBI GEO"),
        "repository": more_result.get("repository", GEO_REPOSITORY),
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
        repository=GEO_REPOSITORY,
    )


def dataset_search_result_payload(result: DatasetSearchResult) -> dict:
    """Serialize a dataset search result with agent context export."""
    payload = result.model_dump()
    payload["agent_context"] = export_dataset_search_agent_context(result)
    return payload
