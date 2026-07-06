"""Tests for asthma / PBMC / flow cytometry query interpretation and ImmPort search."""

from unittest.mock import patch

from domain.facet_search_strategies import build_facet_search_queries
from domain.query_interpretation import interpret_dataset_query
from tools.immport_dataset_search import (
    TEXT_BROAD_STRATEGY,
    _compact_adhoc_search_term,
    _resolve_search_queries,
    fetch_immport_repository_records,
)


ASTHMA_QUERY = "Find public immunology datasets for asthma PBMC flow cytometry."


def test_asthma_query_interprets_disease_tissue_assay_and_human():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)

    assert interpreted.disease == "asthma"
    assert interpreted.tissue == "PBMC"
    assert interpreted.assay == "Flow Cytometry"
    assert interpreted.organism is None


def test_asthma_query_without_human_does_not_send_species_to_immport():
    def mock_get(url, *args, **kwargs):
        params = kwargs.get("params") or {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "hits": {
                        "total": {"value": 28},
                        "hits": [],
                    }
                }

        return FakeResponse()

    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    with patch("tools.immport_dataset_search.requests.get", side_effect=mock_get) as mock_get_fn:
        fetch_immport_repository_records(
            [],
            max_results=5,
            query=ASTHMA_QUERY,
            interpreted_query=interpreted,
        )

    facet_calls = []
    text_calls = []
    for call in mock_get_fn.call_args_list:
        if "search/study" not in str(call.args[0] if call.args else call.kwargs.get("url", "")):
            continue
        params = call.kwargs.get("params") or {}
        if params.get("term") and not params.get("conditionOrDisease"):
            text_calls.append(params)
        elif params.get("conditionOrDisease"):
            facet_calls.append(params)

    assert facet_calls
    assert all("species" not in params for params in facet_calls)
    assert all("term" not in params for params in facet_calls)
    assert all(params.get("conditionOrDisease") == "asthma" for params in facet_calls)
    assert text_calls
    assert all(params.get("term") == "asthma PBMC flow cytometry" for params in text_calls)
    assert all("conditionOrDisease" not in params for params in text_calls)


def test_asthma_query_with_explicit_human_sends_species_to_immport():
    def mock_get(url, *args, **kwargs):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"hits": {"total": {"value": 20}, "hits": []}}

        return FakeResponse()

    query = "Find public human immunology datasets for asthma PBMC flow cytometry."
    interpreted = interpret_dataset_query(query)
    assert interpreted.organism == "human"

    with patch("tools.immport_dataset_search.requests.get", side_effect=mock_get) as mock_get_fn:
        fetch_immport_repository_records(
            [],
            max_results=5,
            query=query,
            interpreted_query=interpreted,
        )

    assert any(
        (call.kwargs.get("params") or {}).get("species") == "Homo sapiens"
        for call in mock_get_fn.call_args_list
    )


def test_asthma_query_builds_facet_strategies_plus_text_broad():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    queries = _resolve_search_queries(query=ASTHMA_QUERY, interpreted_query=interpreted)

    assert [strategy for strategy, _ in queries] == [
        "strict",
        "broad_1",
        "broad_2",
        "broad_3",
        TEXT_BROAD_STRATEGY,
    ]
    assert queries[0][1] == "asthma Flow Cytometry PBMC"
    assert queries[-1][1] == "asthma PBMC flow cytometry"


def test_asthma_query_builds_four_facet_strategies():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    queries = build_facet_search_queries(interpreted=interpreted)

    assert [strategy for strategy, _ in queries] == [
        "strict",
        "broad_1",
        "broad_2",
        "broad_3",
    ]
    assert queries[0][1] == "asthma Flow Cytometry PBMC"


def test_compact_adhoc_search_term_strips_boilerplate():
    compact = _compact_adhoc_search_term(ASTHMA_QUERY)

    assert compact == "asthma PBMC flow cytometry"
    assert "immunology" not in compact
    assert "datasets" not in compact


def test_resolve_search_queries_omits_text_broad_when_disabled():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    queries = _resolve_search_queries(
        query=ASTHMA_QUERY,
        interpreted_query=interpreted,
        include_text_broad=False,
    )

    assert [strategy for strategy, _ in queries] == [
        "strict",
        "broad_1",
        "broad_2",
        "broad_3",
    ]


def test_fetch_immport_repository_records_respects_include_text_broad_flag():
    responses = {
        "strict": 1,
        "broad_1": 4,
        "broad_2": 12,
        "broad_3": 28,
    }

    def mock_get(url, *args, **kwargs):
        params = kwargs.get("params") or {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                if params.get("conditionOrDisease") and params.get("assayMethod") and params.get("biosampleType"):
                    total = responses["strict"]
                elif params.get("conditionOrDisease") and params.get("assayMethod"):
                    total = responses["broad_1"]
                elif params.get("conditionOrDisease") and params.get("biosampleType"):
                    total = responses["broad_2"]
                elif params.get("conditionOrDisease"):
                    total = responses["broad_3"]
                elif params.get("term"):
                    total = 55
                else:
                    total = 0
                page_size = int(params.get("pageSize", 0))
                from_record = int(params.get("fromRecord", 1))
                hits = []
                if page_size > 0:
                    for offset in range(page_size):
                        accession_num = from_record + offset
                        hits.append(
                            {
                                "_source": {
                                    "study_accession": f"SDY{accession_num}",
                                    "brief_title": f"Asthma PBMC flow {accession_num}",
                                    "brief_description": "Asthma PBMC flow cytometry study",
                                    "condition_or_disease": ["asthma"],
                                    "biosample_type": ["PBMC"],
                                    "assay_method": ["Flow Cytometry"],
                                    "species": ["Homo sapiens"],
                                }
                            }
                        )
                return {
                    "hits": {
                        "total": {"value": total},
                        "hits": hits,
                    }
                }

        return FakeResponse()

    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    with patch("tools.immport_dataset_search.requests.get", side_effect=mock_get):
        result = fetch_immport_repository_records(
            [],
            max_results=5,
            query=ASTHMA_QUERY,
            interpreted_query=interpreted,
            include_text_broad=True,
        )

    assert result["primary_total_found"] == 1
    assert result["total_found"] == 28
    assert len(result["search_strategies"]) == 5
    assert result["search_strategies"][-1]["strategy"] == TEXT_BROAD_STRATEGY
    assert result["search_strategies"][-1]["supplemental"] is True
    assert result["include_text_broad"] is True
    assert result["text_broad_total_found"] == 55
    assert result["search_term"] == "asthma Flow Cytometry PBMC"
    assert result["has_more"] is True
    assert result["load_more_cursor"] is not None
    assert result["load_more_cursor"]["include_text_broad"] is True
    assert result["load_more_cursor"]["text_broad_total_found"] == 55


def test_fetch_immport_repository_records_skips_text_broad_when_disabled():
    def mock_get(url, *args, **kwargs):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"hits": {"total": {"value": 28}, "hits": []}}

        return FakeResponse()

    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    with patch("tools.immport_dataset_search.requests.get", side_effect=mock_get):
        result = fetch_immport_repository_records(
            [],
            max_results=5,
            query=ASTHMA_QUERY,
            interpreted_query=interpreted,
            include_text_broad=False,
        )

    assert len(result["search_strategies"]) == 4
    assert result["include_text_broad"] is False
    assert result.get("text_broad_total_found") is None
    assert result["load_more_cursor"]["include_text_broad"] is False
