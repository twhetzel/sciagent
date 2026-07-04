"""Tests for multi-strategy GEO search count behavior."""

from __future__ import annotations

from unittest.mock import patch

from domain.dataset_search import ConceptMapping
from tools.geo_dataset_search import fetch_geo_repository_records


def _uc_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="ulcerative colitis",
            curie="MONDO:0005101",
            label="ulcerative colitis",
            ontology="MONDO",
            synonyms=["ulcerative colitis", "colitis ulcerative"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="colon",
            curie="UBERON:0001155",
            label="colon",
            ontology="UBERON",
            synonyms=["colon", "colonic"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0002117",
            label="RNA-seq",
            ontology="OBI",
            synonyms=["RNA-seq", "RNA sequencing"],
            source="curated",
        ),
    ]


def test_all_strategy_esearch_counts_run_before_retrieval_quota_filled():
    count_calls: list[tuple[str, int]] = []
    collect_calls = 0

    def fake_esearch(search_term: str, retmax: int, *, retstart: int = 0):
        count_calls.append((search_term, retmax))
        if retmax == 0:
            if "colonic" in search_term or "large intestine" in search_term:
                if "rna" in search_term:
                    return ([], 129)
                return ([], 2975)
            if "rna" in search_term:
                return ([], 175)
            return ([], 6052)
        if "rna" in search_term and "colonic" not in search_term:
            return (
                [f"id-b1-{index}" for index in range(retmax)],
                175,
            )
        return ([f"id-{retstart}"] * retmax, 129)

    def fake_collect(*args, **kwargs):
        nonlocal collect_calls
        collect_calls += 1
        return (
            [f"id-b1-{index}" for index in range(15)],
            {f"id-b1-{index}": ("strict", "term") for index in range(15)},
            {"strict": 15, "broad_1": 0, "broad_2": 0, "broad_3": 0},
            [{"strategy": "strict", "search_term": "term", "total_found": 129, "retrieved": 15, "new_ids": 15}],
        )

    with patch("tools.geo_dataset_search._geo_esummary", return_value=[]):
        with patch("tools.geo_dataset_search._geo_esearch", side_effect=fake_esearch):
            with patch("tools.geo_dataset_search._collect_geo_id_batch", side_effect=fake_collect):
                result = fetch_geo_repository_records(_uc_mappings(), max_results=15)

    assert collect_calls == 1
    assert len([call for call in count_calls if call[1] == 0]) == 4
    assert result["total_found"] == 6052
    assert result["primary_total_found"] == 129
    assert result["has_more"] is True
    assert result["load_more_cursor"] is not None
