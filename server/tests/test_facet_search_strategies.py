"""Tests for shared facet search strategies."""

from domain.dataset_search import InterpretedQuery
from domain.facet_search_strategies import build_interpreted_facet_queries


def test_build_interpreted_facet_queries_matches_geo_strategy_shape():
    interpreted = InterpretedQuery(
        disease="ulcerative colitis",
        tissue="colon",
        assay="RNA-seq",
        organism="human",
    )
    queries = build_interpreted_facet_queries(interpreted)

    assert queries == [
        ("strict", "ulcerative colitis RNA-seq colon"),
        ("broad_1", "ulcerative colitis RNA-seq"),
        ("broad_2", "ulcerative colitis colon"),
        ("broad_3", "ulcerative colitis"),
    ]


def test_build_interpreted_facet_queries_uses_available_slots_per_strategy():
    interpreted = InterpretedQuery(disease="ulcerative colitis")
    queries = build_interpreted_facet_queries(interpreted)

    # Mirrors GEO: each strategy uses whichever requested slots are available.
    assert queries == [
        ("strict", "ulcerative colitis"),
        ("broad_1", "ulcerative colitis"),
        ("broad_2", "ulcerative colitis"),
        ("broad_3", "ulcerative colitis"),
    ]
