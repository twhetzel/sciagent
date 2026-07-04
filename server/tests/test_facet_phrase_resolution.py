"""Tests for phrase-based facet resolution during dataset query interpretation."""

from __future__ import annotations

from domain.ontology_grounding import build_geo_search_queries, enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query


def test_crohns_ileum_query_resolves_all_facets_and_builds_four_strategies():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets for Crohn's disease ileum tissue."
    )

    assert interpreted.disease == "Crohn's disease"
    assert interpreted.tissue == "ileum"
    assert interpreted.assay == "RNA-seq"
    assert interpreted.organism == "human"

    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    strategies = build_geo_search_queries(mappings)

    assert len(strategies) == 4
    assert strategies[0][0] == "strict"
    assert "crohn" in strategies[0][1].lower()
    assert "ileum" in strategies[0][1].lower()


def test_uc_query_still_resolves_via_abbreviation_pass():
    interpreted = interpret_dataset_query(
        "Find public RNA-seq datasets for UC colon tissue."
    )

    assert interpreted.disease == "UC"
    assert interpreted.tissue == "colon"

    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    assert len(build_geo_search_queries(mappings)) == 4
