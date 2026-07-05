"""Tests for ImmPort dataset search connector."""

from unittest.mock import patch

from tools.immport_dataset_search import (
    fetch_immport_repository_records,
    normalize_immport_record,
    search_immport_datasets,
)


IMMPORT_SEARCH_RESPONSE = {
    "hits": {
        "total": {"value": 2, "relation": "eq"},
        "hits": [
            {
                "_source": {
                    "study_accession": "SDY1365",
                    "brief_title": "UC MAIT study",
                    "brief_description": "Establish whether MAIT cells participate in pathophysiology of UC",
                    "condition_or_disease": ["ulcerative colitis"],
                    "biosample_type": ["Colon"],
                    "assay_method": ["RNA-seq"],
                    "species": ["Homo sapiens"],
                    "research_focus": ["Autoimmune"],
                    "actual_enrollment": 13,
                    "doi": "10.21430/M3AV8VFYCB",
                    "pubmed_id": ["30123456"],
                    "latest_data_release_version": "DR58",
                    "latest_data_release_date": "2025-10-30",
                }
            },
            {
                "_source": {
                    "study_accession": "SDY999",
                    "brief_title": "Other study",
                    "brief_description": "Unrelated",
                    "condition_or_disease": ["asthma"],
                    "species": ["Homo sapiens"],
                }
            },
        ],
    }
}


def _mock_get(url, *args, **kwargs):
    params = kwargs.get("params") or {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            page_size = int(params.get("pageSize", 0))
            hits = IMMPORT_SEARCH_RESPONSE["hits"]["hits"] if page_size > 0 else []
            return {
                "hits": {
                    "total": IMMPORT_SEARCH_RESPONSE["hits"]["total"],
                    "hits": hits,
                }
            }

    return FakeResponse()


def test_search_immport_datasets_returns_parsed_results():
    with patch("tools.immport_dataset_search.requests.get", side_effect=_mock_get):
        result = search_immport_datasets("ulcerative colitis RNA-seq colon", max_results=5)

    assert result["total_found"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["accession"] == "SDY1365"
    assert result["results"][0]["url"].endswith("/shared/study/SDY1365")
    assert result["source"] == "ImmPort"


def test_normalize_immport_record_populates_candidate_fields():
    record = {
        "accession": "SDY1365",
        "title": "UC MAIT study",
        "description": "Establish whether MAIT cells participate in pathophysiology of UC",
        "summary": "Establish whether MAIT cells participate in pathophysiology of UC. ulcerative colitis",
        "condition_or_disease": "ulcerative colitis",
        "biosample_type": "Colon",
        "assay_method": "RNA-seq",
        "species": "Homo sapiens",
        "research_focus": "Autoimmune",
        "doi": "10.21430/M3AV8VFYCB",
        "url": "https://www.immport.org/shared/study/SDY1365",
        "sample_count": 13,
    }

    candidate = normalize_immport_record(record)

    assert candidate is not None
    assert candidate.repository == "ImmPort"
    assert candidate.observed_disease == "ulcerative colitis"
    assert candidate.observed_tissue == "Colon"
    assert candidate.observed_assay == "RNA-seq"
    assert candidate.observed_organism == "Homo sapiens"
    assert candidate.source_metadata["source"] == "ImmPort"
    assert candidate.source_metadata["doi"] == "10.21430/M3AV8VFYCB"


def test_fetch_immport_repository_records_uses_multi_strategy_search():
    with patch("tools.immport_dataset_search.resolve_immport_facet_value", side_effect=lambda slot, value: value):
        with patch("tools.immport_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
            result = fetch_immport_repository_records(
                [],
                max_results=5,
                query="Find public RNA-seq datasets for ulcerative colitis colon tissue",
                interpreted_query={
                    "disease": "ulcerative colitis",
                    "tissue": "colon",
                    "assay": "RNA-seq",
                    "organism": "human",
                },
            )

    assert result["repository"] == "ImmPort"
    assert result["records"]
    assert result["search_strategies"]
    assert mock_get.call_count >= 1
    first_params = mock_get.call_args_list[0].kwargs["params"]
    assert "term" not in first_params
    assert first_params.get("conditionOrDisease") == "ulcerative colitis"
    assert first_params.get("species") == "Homo sapiens"
