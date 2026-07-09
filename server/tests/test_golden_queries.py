"""Tests for the golden-query dataset discovery evaluation harness."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agent.dataset_discovery import GEO_REPOSITORY, GXA_REPOSITORY
from domain.dataset_search import ConceptMapping
from domain.ontology_grounding import ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from evaluation.golden_queries import (
    GOLDEN_QUERIES,
    evaluate_all_golden_queries,
    evaluate_golden_query,
    format_report_text,
    resolve_enabled_dataset_repositories,
)


def _uc_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="ulcerative colitis",
            curie="MONDO:0005101",
            label="ulcerative colitis",
            ontology="MONDO",
            match_type="exact",
            source="curated",
            confidence=0.95,
        ),
        ConceptMapping(
            slot="tissue",
            query_term="colon",
            curie="UBERON:0001155",
            label="colon",
            ontology="UBERON",
            match_type="exact",
            source="curated",
            confidence=0.95,
        ),
        ConceptMapping(
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0000630",
            label="RNA-seq",
            ontology="OBI",
            match_type="exact",
            source="curated",
            confidence=0.95,
        ),
    ]


def _geo_search_result() -> dict:
    return {
        "search_term": "ulcerative colitis RNA-seq colon",
        "search_strategies": [
            {
                "strategy": "strict",
                "search_term": "ulcerative colitis RNA-seq colon",
                "total_found": 5,
                "retrieved": 1,
                "new_ids": 1,
            }
        ],
        "total_found": 5,
        "primary_total_found": 1,
        "max_results": 10,
        "records": [
            {
                "accession": "GSE57945",
                "title": "GEO pediatric IBD cohort",
                "summary": "RNA-seq pediatric IBD cohort colon ulcerative colitis",
            }
        ],
        "source": "NCBI GEO",
        "repository": GEO_REPOSITORY,
        "has_more": False,
    }


def _gxa_search_result() -> dict:
    return {
        "search_term": "ulcerative colitis RNA-seq colon",
        "search_strategies": [
            {
                "strategy": "strict",
                "search_term": "ulcerative colitis RNA-seq colon",
                "total_found": 20,
                "retrieved": 1,
                "new_ids": 1,
            }
        ],
        "total_found": 20,
        "primary_total_found": 1,
        "max_results": 10,
        "records": [
            {
                "accession": "E-MTAB-7860",
                "title": "GXA UC biopsies",
                "description": "RNA-seq UC biopsies colon ulcerative colitis",
                "species": "Homo sapiens",
                "experiment_type": "rnaseq_mrna_differential",
                "url": "https://www.ebi.ac.uk/gxa/experiments/E-MTAB-7860",
            }
        ],
        "source": "Expression Atlas",
        "repository": GXA_REPOSITORY,
        "has_more": False,
    }


def test_golden_queries_contains_initial_set():
    assert len(GOLDEN_QUERIES) == 4
    assert any("ulcerative colitis" in query for query in GOLDEN_QUERIES)
    assert any("UC colon" in query for query in GOLDEN_QUERIES)
    assert any("Crohn" in query for query in GOLDEN_QUERIES)
    assert any("Alzheimer" in query for query in GOLDEN_QUERIES)


def test_resolve_enabled_dataset_repositories_respects_blocklist():
    with patch("evaluation.golden_queries.is_source_enabled", side_effect=lambda name: name != "geo_dataset_search"):
        assert resolve_enabled_dataset_repositories() == [GXA_REPOSITORY]


def test_evaluate_golden_query_report_shape():
    query = GOLDEN_QUERIES[0]
    repositories = [GEO_REPOSITORY, GXA_REPOSITORY]

    with patch("evaluation.golden_queries.ground_query", return_value=_uc_mappings()):
        with patch(
            "evaluation.golden_queries.search_repository",
            side_effect=[_geo_search_result(), _gxa_search_result()],
        ):
            report = evaluate_golden_query(query, repositories=repositories, max_results=10)

    assert report["query"] == query
    assert report["enabled_sources"] == repositories
    assert report["interpreted_facets"]["disease"] == "ulcerative colitis"
    assert report["interpreted_facets"]["tissue"] == "colon"
    assert report["interpreted_facets"]["assay"] == "RNA-seq"
    assert len(report["grounded_concepts"]) == 3
    assert report["per_source_hit_counts"] == {GEO_REPOSITORY: 5, GXA_REPOSITORY: 20}
    assert len(report["top_10"]) <= 10
    assert report["top_10_source_distribution"]
    assert report["match_statuses"]
    assert "warnings_count" in report
    assert "conflicts_count" in report
    assert report["context_export_ok"] is True
    assert "context_export_error" not in report
    assert report.get("assay_ranking_violations") == []
    assert report.get("assay_ranking_ok") is True
    for index in range(len(report["top_10"]) - 1):
        current = report["top_10"][index]["display_rank_score"]
        following = report["top_10"][index + 1]["display_rank_score"]
        assert current >= following


def test_evaluate_golden_query_no_enabled_sources():
    report = evaluate_golden_query(GOLDEN_QUERIES[0], repositories=[])
    assert report["error"]
    assert report["context_export_ok"] is False


def test_format_report_text_includes_key_sections():
    report = {
        "query": GOLDEN_QUERIES[0],
        "enabled_sources": [GEO_REPOSITORY],
        "interpreted_facets": {"disease": "ulcerative colitis", "tissue": "colon", "assay": "RNA-seq"},
        "grounded_concepts": [{"slot": "disease", "label": "ulcerative colitis", "curie": "MONDO:0005101", "match_type": "exact", "source": "curated", "confidence": 0.95}],
        "per_source_hit_counts": {GEO_REPOSITORY: 5},
        "top_10": [{"rank": 1, "accession": "GSE57945", "title": "Example", "repository": GEO_REPOSITORY, "score": 0.9, "match_status": "full"}],
        "top_10_source_distribution": {GEO_REPOSITORY: 1},
        "match_statuses": {"full": 1},
        "warnings_count": 0,
        "conflicts_count": 0,
        "context_export_ok": True,
        "integrated_total_found": 5,
        "integrated_retrieved_count": 1,
    }
    text = format_report_text(report)
    assert "Query:" in text
    assert "Per-source hit counts" in text
    assert "Top 10 source distribution" in text
    assert "Context export OK" in text


def test_evaluate_all_golden_queries_runs_each_query():
    with patch("evaluation.golden_queries.evaluate_golden_query", return_value={"query": "x", "context_export_ok": True}) as mock_eval:
        with patch("evaluation.golden_queries.time.sleep") as mock_sleep:
            reports = evaluate_all_golden_queries(("q1", "q2"), pause_between_queries_sec=2.0)
    assert len(reports) == 2
    assert mock_eval.call_count == 2
    mock_sleep.assert_called_once_with(2.0)


def test_evaluate_golden_query_uses_harness_default_max_results():
    with patch("evaluation.golden_queries.ground_query", return_value=_uc_mappings()):
        with patch("evaluation.golden_queries.search_repository", side_effect=[_geo_search_result(), _gxa_search_result()]) as mock_search:
            report = evaluate_golden_query(GOLDEN_QUERIES[0], repositories=[GEO_REPOSITORY, GXA_REPOSITORY])
    assert report["max_results"] == 10
    assert mock_search.call_args_list[0].kwargs["max_results"] == 10


def test_golden_alzheimers_brain_query_interprets_and_grounds_tissue():
    query = GOLDEN_QUERIES[3]
    interpreted = interpret_dataset_query(query)
    assert interpreted.disease == "Alzheimer disease"
    assert interpreted.tissue == "brain"
    assert interpreted.assay == "RNA-seq"
    assert interpreted.organism is None

    mappings = ground_interpreted_query(interpreted)
    tissue = next(mapping for mapping in mappings if mapping.slot == "tissue")
    assert tissue.ontology == "UBERON"
    assert tissue.curie == "UBERON:0000955"


@pytest.mark.skipif(
    os.environ.get("SCIAGENT_RUN_GOLDEN_QUERIES") != "1",
    reason="Set SCIAGENT_RUN_GOLDEN_QUERIES=1 to run live repository evaluation",
)
def test_golden_queries_live_against_enabled_sources():
    """Live smoke test against GEO and/or Expression Atlas (network required)."""
    repositories = resolve_enabled_dataset_repositories()
    if not repositories:
        pytest.skip("No dataset sources enabled")

    report = evaluate_golden_query(GOLDEN_QUERIES[0], repositories=repositories)
    assert not report.get("error")
    assert report["context_export_ok"] is True
    assert report["enabled_sources"] == repositories
    assert isinstance(report["per_source_hit_counts"], dict)
    assert isinstance(report["top_10"], list)
