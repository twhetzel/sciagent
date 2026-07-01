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

This path does NOT use tools/ontology_normalizer.py. That module powers the generic
gene/literature/ClinVar "normalize" trace step, which is a different concern.
"""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import DatasetSearchResult, InterpretedQuery
from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from domain.ranking import rank_annotated_candidates
from tools.geo_dataset_search import (
    fetch_geo_repository_records,
    normalize_geo_records,
)


def interpret_query(query: str) -> InterpretedQuery:
    """Step 1: extract structured facets from the user query."""
    return interpret_dataset_query(query)


def ground_query(interpreted: InterpretedQuery):
    """Step 2: provider-based ontology grounding of requested facets."""
    return enrich_concept_mappings(ground_interpreted_query(interpreted))


def search_repository(concept_mappings, max_results: int = 15) -> dict:
    """Step 3: search GEO using grounded labels and synonyms."""
    return fetch_geo_repository_records(concept_mappings, max_results=max_results)


def normalize_records(raw_records: list[dict]) -> list:
    """Step 4: repository record normalization into shared DatasetCandidate models."""
    return normalize_geo_records(raw_records)


def annotate_evidence(candidates, concept_mappings):
    """Step 5: annotate returned records with evidence snippets and warnings."""
    return annotate_dataset_candidates(candidates, concept_mappings)


def rank_results(candidates, concept_mappings):
    """Step 6: rank annotated candidates by evidence coverage."""
    return rank_annotated_candidates(candidates, concept_mappings)


def run_dataset_discovery(query: str, max_results: int = 15) -> DatasetSearchResult:
    """Run the full dataset-discovery pipeline."""
    interpreted = interpret_query(query)
    concept_mappings = ground_query(interpreted)
    search_result = search_repository(concept_mappings, max_results=max_results)
    candidates = normalize_records(search_result.get("records", []))
    annotated = annotate_evidence(candidates, concept_mappings)
    ranked = rank_results(annotated, concept_mappings)

    return DatasetSearchResult(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        candidates=ranked,
        total_found=search_result.get("total_found", len(ranked)),
        source=search_result.get("source", "NCBI GEO"),
        repository=search_result.get("repository", "GEO"),
        search_term=search_result.get("search_term") or None,
        search_strategies=search_result.get("search_strategies", []),
    )
