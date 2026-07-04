"""Tests for abbreviation resolution during dataset query interpretation."""

from __future__ import annotations

from domain.ontology_grounding import build_geo_search_queries, enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query


def test_uc_colon_query_resolves_disease_and_builds_four_strategies():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets for UC colon tissue."
    )

    assert interpreted.disease == "UC"
    assert interpreted.tissue == "colon"
    assert interpreted.assay == "RNA-seq"
    assert interpreted.organism == "human"

    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    strategies = build_geo_search_queries(mappings)

    assert len(strategies) == 4
    assert strategies[0][0] == "strict"
    assert "ulcerative colitis" in strategies[0][1].lower()
    assert " UC " not in f" {strategies[0][1]} "
    assert "uc OR" not in strategies[0][1].lower()


def test_uc_without_clinical_context_is_not_resolved_as_disease():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets collected at UC Berkeley."
    )

    assert interpreted.disease is None
    assert interpreted.assay == "RNA-seq"


def test_full_disease_name_still_works():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets for ulcerative colitis colon tissue."
    )

    assert interpreted.disease == "ulcerative colitis"
    assert interpreted.tissue == "colon"
    assert interpreted.assay == "RNA-seq"

    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    assert len(build_geo_search_queries(mappings)) == 4
