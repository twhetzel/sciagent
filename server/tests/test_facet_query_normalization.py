"""Tests for punctuation-tolerant facet query normalization and interpretation."""

from __future__ import annotations

from domain.facet_query_normalization import (
    grounding_phrase_variants,
    normalize_query_for_phrases,
)
from domain.ontology_grounding import build_geo_search_queries, enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query


def test_normalize_query_strips_parentheticals_and_clause_delimiters():
    normalized = normalize_query_for_phrases(
        "Find RNA-seq datasets for Crohn's disease; ileum, colon tissue (UC)."
    )
    assert "(" not in normalized
    assert ")" not in normalized
    assert ";" not in normalized
    assert "Crohn's disease" in normalized
    assert "ileum" in normalized


def test_grounding_variants_include_spaced_and_apostrophe_forms():
    variants = grounding_phrase_variants("ulcerative-colitis")
    assert "ulcerative-colitis" in variants
    assert "ulcerative colitis" in variants

    apostrophe_variants = grounding_phrase_variants("Parkinson's disease")
    assert "Parkinson's disease" in apostrophe_variants
    assert "Parkinson disease" in apostrophe_variants


def test_hyphenated_disease_resolves_to_four_strategies():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets for ulcerative-colitis ileum tissue."
    )

    assert interpreted.disease == "ulcerative colitis"
    assert interpreted.tissue == "ileum"
    assert interpreted.assay == "RNA-seq"

    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    assert len(build_geo_search_queries(mappings)) == 4


def test_parkinson_parenthetical_and_two_word_tissue_resolve():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets for Parkinson's disease (PD) substantia nigra tissue."
    )

    assert interpreted.disease == "Parkinson's disease"
    assert interpreted.tissue == "substantia nigra"
    assert interpreted.assay == "RNA-seq"

    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    strategies = build_geo_search_queries(mappings)
    assert len(strategies) == 4
    assert "parkinson" in strategies[0][1].lower()
    assert "substantia nigra" in strategies[0][1].lower()
