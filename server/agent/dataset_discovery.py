"""End-to-end ontology-grounded dataset discovery pipeline."""

from __future__ import annotations

from domain.dataset_search import DatasetSearchResult
from domain.ontology_grounding import ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from domain.ranking import rank_dataset_candidates
from tools.geo_dataset_search import search_geo_datasets


def run_dataset_discovery(query: str, max_results: int = 15) -> DatasetSearchResult:
    """Interpret, ground, search GEO, rank, and return normalized dataset results."""
    interpreted = interpret_dataset_query(query)
    concept_mappings = ground_interpreted_query(interpreted)

    geo_result = search_geo_datasets(concept_mappings, max_results=max_results)
    raw_candidates = geo_result.get("candidates", [])
    ranked = rank_dataset_candidates(
        raw_candidates,
        concept_mappings,
        requested_assay=interpreted.assay,
    )

    return DatasetSearchResult(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        candidates=ranked,
        total_found=geo_result.get("total_found", len(ranked)),
        source=geo_result.get("source", "NCBI GEO"),
    )
