"""
Ontology-grounded GEO dataset discovery pipeline.

Pipeline steps (dataset-discovery path only):
  1. Interpret Query      — extract disease, tissue, assay, organism facets
  2. Ground Query         — map requested facets via OLS/BioPortal/LLM with curated fallback
  3. Search Repository    — multi-strategy GEO search using grounded labels/synonyms
  4. Normalize Records    — convert GEO API payloads into shared DatasetCandidate models
  5. Annotate Evidence    — field-level concept/evidence matching on returned records
  6. Rank Results         — score by evidence coverage
  7. Respond              — formatted response + structured dataset_search payload
"""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_context_export import export_dataset_search_agent_context
from domain.dataset_search import (
    DatasetCandidate,
    DatasetSearchCursor,
    DatasetSearchResult,
    InterpretedQuery,
)
from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from domain.ranking import rank_annotated_candidates
from tools.geo_dataset_search import (
    fetch_geo_repository_records,
    fetch_more_geo_repository_records,
    get_geo_max_results,
    normalize_geo_records,
)


def interpret_query(query: str) -> InterpretedQuery:
    """Step 1: extract structured facets from the user query."""
    return interpret_dataset_query(query)


def ground_query(interpreted: InterpretedQuery):
    """Step 2: provider-based ontology grounding of requested facets."""
    return enrich_concept_mappings(ground_interpreted_query(interpreted))


def search_repository(
    concept_mappings,
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
) -> dict:
    """Step 3: search GEO using grounded labels and synonyms."""
    return fetch_geo_repository_records(
        concept_mappings,
        max_results=max_results,
        query=query,
        interpreted_query=(
            interpreted_query.model_dump() if interpreted_query is not None else None
        ),
    )


def normalize_records(raw_records: list[dict]) -> list:
    """Step 4: repository record normalization into shared DatasetCandidate models."""
    return normalize_geo_records(raw_records)


def annotate_evidence(candidates, concept_mappings):
    """Step 5: annotate returned records with evidence snippets and warnings."""
    return annotate_dataset_candidates(candidates, concept_mappings)


def rank_results(candidates, concept_mappings):
    """Step 6: rank annotated candidates by evidence coverage."""
    return rank_annotated_candidates(candidates, concept_mappings)


def _build_dataset_search_result(
    *,
    query: str,
    interpreted: InterpretedQuery,
    concept_mappings,
    ranked: list[DatasetCandidate],
    search_result: dict,
) -> DatasetSearchResult:
    cursor_payload = search_result.get("load_more_cursor")
    cursor = (
        DatasetSearchCursor.model_validate(cursor_payload)
        if cursor_payload is not None
        else None
    )
    return DatasetSearchResult(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        candidates=ranked,
        total_found=search_result.get("total_found", len(ranked)),
        primary_total_found=search_result.get("primary_total_found"),
        max_results=search_result.get("max_results"),
        source=search_result.get("source", "NCBI GEO"),
        repository=search_result.get("repository", "GEO"),
        search_term=search_result.get("search_term") or None,
        search_strategies=search_result.get("search_strategies", []),
        has_more=search_result.get("has_more", False),
        retrieved_count=len(ranked),
        load_more_cursor=cursor,
    )


def run_dataset_discovery(query: str, max_results: int | None = None) -> DatasetSearchResult:
    """Run the full dataset-discovery pipeline."""
    resolved_max_results = get_geo_max_results(max_results)
    interpreted = interpret_query(query)
    concept_mappings = ground_query(interpreted)
    search_result = search_repository(
        concept_mappings,
        max_results=resolved_max_results,
        query=query,
        interpreted_query=interpreted,
    )
    candidates = normalize_records(search_result.get("records", []))
    annotated = annotate_evidence(candidates, concept_mappings)
    ranked = rank_results(annotated, concept_mappings)
    return _build_dataset_search_result(
        query=query,
        interpreted=interpreted,
        concept_mappings=concept_mappings,
        ranked=ranked,
        search_result=search_result,
    )


def load_more_dataset_search(
    cursor: DatasetSearchCursor,
    existing_candidates: list[DatasetCandidate],
) -> DatasetSearchResult:
    """
    Fetch the next GEO batch, merge with prior candidates, and re-rank all.

    Existing candidates must already be annotated/ranked from a prior response.
    """
    more_result = fetch_more_geo_repository_records(cursor)
    if more_result.get("error") and not more_result.get("records"):
        raise RuntimeError(more_result["error"])

    new_candidates = normalize_records(more_result.get("records", []))
    new_annotated = annotate_evidence(new_candidates, cursor.concept_mappings)
    merged = list(existing_candidates) + new_annotated
    ranked = rank_results(merged, cursor.concept_mappings)

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
        "repository": more_result.get("repository", "GEO"),
        "search_term": cursor.search_term,
        "search_strategies": [],
        "has_more": more_result.get("has_more", False),
        "load_more_cursor": updated_cursor.model_dump(),
    }
    result = _build_dataset_search_result(
        query=cursor.query,
        interpreted=cursor.interpreted_query,
        concept_mappings=cursor.concept_mappings,
        ranked=ranked,
        search_result=search_result,
    )
    return result


def dataset_search_result_payload(result: DatasetSearchResult) -> dict:
    """Serialize a dataset search result with agent context export."""
    payload = result.model_dump()
    payload["agent_context"] = export_dataset_search_agent_context(result)
    return payload
