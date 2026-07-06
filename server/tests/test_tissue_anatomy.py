"""Tests for anatomy/tissue facet interpretation and grounding."""

from __future__ import annotations

import pytest

from domain.ontology_grounding import (
    build_geo_search_queries,
    enrich_concept_mappings,
    ground_interpreted_query,
)
from domain.query_interpretation import interpret_dataset_query
from domain.synonym_classification import retrieval_terms_for_mapping
from domain.tissue_anatomy import ANATOMY_TERMS
from evaluation.golden_queries import GOLDEN_QUERIES


@pytest.mark.parametrize(
    ("query", "expected_tissue"),
    [
        ("Find public RNA-seq datasets for Alzheimer's disease brain tissue.", "brain"),
        ("Find RNA-seq datasets for Alzheimer disease hippocampus tissue.", "hippocampus"),
        ("Find RNA-seq datasets for Parkinson's disease cortex tissue.", "cortex"),
        ("Find RNA-seq datasets for liver tissue.", "liver"),
        ("Find RNA-seq datasets for kidney tissue.", "kidney"),
        ("Find RNA-seq datasets for lung tissue.", "lung"),
        ("Find RNA-seq datasets for heart tissue.", "heart"),
        ("Find RNA-seq datasets for blood tissue.", "blood"),
        ("Find RNA-seq datasets for skin tissue.", "skin"),
        ("Find RNA-seq datasets for muscle tissue.", "muscle"),
        ("Find RNA-seq datasets for tumor tissue.", "tumor"),
    ],
)
def test_common_anatomy_terms_are_interpreted(query: str, expected_tissue: str):
    interpreted = interpret_dataset_query(query)
    assert interpreted.tissue == expected_tissue


def test_alzheimers_brain_golden_query_interprets_all_facets():
    interpreted = interpret_dataset_query(GOLDEN_QUERIES[3])

    assert interpreted.disease == "Alzheimer disease"
    assert interpreted.tissue == "brain"
    assert interpreted.assay == "RNA-seq"
    assert interpreted.organism is None


def test_alzheimers_brain_golden_query_grounds_tissue_to_uberon_with_safe_terms():
    interpreted = interpret_dataset_query(GOLDEN_QUERIES[3])
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    tissue = next(mapping for mapping in mappings if mapping.slot == "tissue")

    assert tissue.query_term == "brain"
    assert tissue.ontology == "UBERON"
    assert tissue.curie == "UBERON:0000955"

    retrieval_terms = retrieval_terms_for_mapping(tissue)
    assert "brain" in retrieval_terms
    assert "central nervous system" not in retrieval_terms
    assert "nervous system" not in retrieval_terms

    strict_query = build_geo_search_queries(mappings)[0][1].lower()
    assert "brain" in strict_query
    assert "alzheimer" in strict_query


def test_anatomy_seed_count_matches_documented_terms():
    assert {entry["canonical"] for entry in ANATOMY_TERMS} == {
        "brain",
        "cortex",
        "hippocampus",
        "blood",
        "PBMC",
        "T cell",
        "B cell",
        "NK cell",
        "liver",
        "lung",
        "kidney",
        "colon",
        "ileum",
        "heart",
        "muscle",
        "skin",
        "tumor",
    }
