"""Tests for shared text_broad supplemental search helpers."""

from domain.dataset_search import InterpretedQuery
from domain.text_broad_search import (
    TEXT_BROAD_STRATEGY,
    finalize_facet_total_found,
    resolve_search_queries_with_text_broad,
    resolve_text_broad_total_found,
    roll_up_facet_totals,
    strategy_count_summary,
)


def _compact(query: str) -> str:
    return " ".join(query.split()[:3])


def test_resolve_search_queries_appends_text_broad_after_facets():
    interpreted = InterpretedQuery(disease="asthma", tissue="PBMC", assay="flow cytometry")
    queries = resolve_search_queries_with_text_broad(
        query="Find asthma PBMC flow cytometry datasets",
        interpreted_query=interpreted,
        include_text_broad=True,
        compact_adhoc_search_term=_compact,
    )
    assert [strategy for strategy, _ in queries] == [
        "strict",
        "broad_1",
        "broad_2",
        "broad_3",
        TEXT_BROAD_STRATEGY,
    ]
    assert queries[-1][1] == "Find asthma PBMC"


def test_resolve_search_queries_omits_text_broad_when_disabled():
    interpreted = InterpretedQuery(disease="asthma", tissue="PBMC", assay="flow cytometry")
    queries = resolve_search_queries_with_text_broad(
        query="Find asthma PBMC flow cytometry datasets",
        interpreted_query=interpreted,
        include_text_broad=False,
        compact_adhoc_search_term=_compact,
    )
    assert TEXT_BROAD_STRATEGY not in {strategy for strategy, _ in queries}


def test_roll_up_facet_totals_excludes_text_broad():
    max_facet, primary = roll_up_facet_totals(
        TEXT_BROAD_STRATEGY,
        1200,
        max_facet_total_found=40,
        primary_total_found=40,
    )
    assert max_facet == 40
    assert primary == 40

    max_facet, primary = roll_up_facet_totals(
        "strict",
        55,
        max_facet_total_found=max_facet,
        primary_total_found=primary,
    )
    assert max_facet == 55
    assert primary == 40


def test_finalize_facet_total_found_ignores_text_broad_fallback():
    totals = {"strict": 0, TEXT_BROAD_STRATEGY: 99}
    assert finalize_facet_total_found(0, totals) == 0


def test_strategy_count_summary_marks_supplemental():
    summary = strategy_count_summary(TEXT_BROAD_STRATEGY, "asthma pbmc", 12)
    assert summary["supplemental"] is True
    assert resolve_text_broad_total_found(
        {TEXT_BROAD_STRATEGY: 12},
        include_text_broad=True,
    ) == 12
