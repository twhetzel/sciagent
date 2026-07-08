"""Integration-style test for breast cancer OmicsDI query interpretation and search params."""

from unittest.mock import patch

from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from domain.text_broad_search import TEXT_BROAD_STRATEGY
from tools.omicsdi_dataset_search import (
    _build_omicsdi_api_query,
    _resolve_search_queries,
    fetch_omicsdi_repository_records,
)

BREAST_CANCER_QUERY = "Find public proteomics datasets for breast cancer breast tissue"


def test_breast_cancer_query_interprets_disease_and_tissue():
    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    assert interpreted.disease == "breast cancer"
    assert interpreted.tissue == "breast"
    tissue = next(mapping for mapping in mappings if mapping.slot == "tissue")
    assert tissue.curie == "UBERON:0000310"


def test_breast_cancer_query_builds_omicsdi_facet_search():
    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_omicsdi_api_query(
        strategy="strict",
        search_term="breast cancer Proteomics breast",
        concept_mappings=mappings,
        interpreted=interpreted,
        query=BREAST_CANCER_QUERY,
    )

    assert 'disease:"Breast cancer"' in query or 'disease:"breast cancer"' in query.lower()
    assert 'omics_type:"Proteomics"' in query
    assert 'tissue:"Breast"' in query


def test_breast_cancer_query_builds_text_broad_omicsdi_search():
    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_omicsdi_api_query(
        strategy=TEXT_BROAD_STRATEGY,
        search_term="public proteomics breast cancer breast tissue",
        concept_mappings=mappings,
        interpreted=interpreted,
        query=BREAST_CANCER_QUERY,
    )

    assert "public proteomics breast cancer breast tissue" in query
    assert 'disease:"' not in query
    assert 'omics_type:"' not in query


def test_breast_cancer_query_includes_text_broad_strategy():
    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    strategies = [
        strategy
        for strategy, _ in _resolve_search_queries(
            query=BREAST_CANCER_QUERY,
            interpreted_query=interpreted,
            concept_mappings=mappings,
            include_text_broad=True,
        )
    ]
    assert TEXT_BROAD_STRATEGY in strategies


def test_fetch_omicsdi_repository_records_respects_include_text_broad_flag():
    response = {"count": 1, "datasets": []}

    def _mock_get(url, *args, **kwargs):
        params = kwargs.get("params") or {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"count": response["count"], "datasets": []}

        return FakeResponse()

    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    with patch("tools.omicsdi_dataset_search.requests.get", side_effect=_mock_get):
        with patch("tools.omicsdi_dataset_search._fetch_dataset_detail", return_value=None):
            enabled = fetch_omicsdi_repository_records(
                mappings,
                max_results=5,
                query=BREAST_CANCER_QUERY,
                interpreted_query=interpreted,
                include_text_broad=True,
            )
            disabled = fetch_omicsdi_repository_records(
                mappings,
                max_results=5,
                query=BREAST_CANCER_QUERY,
                interpreted_query=interpreted,
                include_text_broad=False,
            )

    enabled_strategies = [item["strategy"] for item in enabled["search_strategies"]]
    disabled_strategies = [item["strategy"] for item in disabled["search_strategies"]]
    assert TEXT_BROAD_STRATEGY in enabled_strategies
    assert TEXT_BROAD_STRATEGY not in disabled_strategies
    assert enabled["include_text_broad"] is True
    assert disabled["include_text_broad"] is False


def test_fetch_omicsdi_repository_records_for_breast_cancer_query():
    response = {
        "count": 1,
        "datasets": [
            {
                "id": "PXD016061",
                "source": "pride",
                "title": "Quantitative proteomic analysis for breast cancer",
                "description": "Proteome data of distant metastatic breast cancer FFPE tissue.",
                "keywords": ["Breast cancer"],
                "organisms": [{"name": "Homo sapiens (Human)"}],
                "omicsType": ["Proteomics"],
            }
        ],
    }

    def _mock_get(url, *args, **kwargs):
        params = kwargs.get("params") or {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                size = int(params.get("size", 0))
                return {
                    "count": response["count"],
                    "datasets": response["datasets"] if size > 0 else [],
                }

        return FakeResponse()

    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    with patch("tools.omicsdi_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        with patch("tools.omicsdi_dataset_search._fetch_dataset_detail", return_value=None):
            result = fetch_omicsdi_repository_records(
                mappings,
                max_results=5,
                query=BREAST_CANCER_QUERY,
                interpreted_query=interpreted,
            )

    assert result["repository"] == "OmicsDI"
    assert result["records"]
    assert result["records"][0]["accession"] == "PXD016061"
    first_query = mock_get.call_args_list[0].kwargs["params"]["query"]
    assert "Proteomics" in first_query
    assert 'tissue:"Breast"' in first_query
