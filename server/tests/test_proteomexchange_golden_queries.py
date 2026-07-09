"""Integration-style tests for ProteomeXchange golden query interpretation and search params."""

from unittest.mock import patch

from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from tools.proteomexchange_dataset_search import (
    _build_proteomexchange_api_query,
    fetch_proteomexchange_repository_records,
)

ALZHEIMER_QUERY = "Find public proteomics datasets for Alzheimer's disease brain tissue."
ASTHMA_QUERY = "Find public proteomics datasets for asthma lung tissue."
BREAST_CANCER_QUERY = "Find public proteomics datasets for breast cancer breast tissue."


def test_alzheimer_brain_query_builds_proteomexchange_facet_search():
    interpreted = interpret_dataset_query(ALZHEIMER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_proteomexchange_api_query(
        strategy="strict",
        search_term="Alzheimer disease Proteomics brain",
        concept_mappings=mappings,
        interpreted=interpreted,
        query=ALZHEIMER_QUERY,
    )

    assert "repository:pride" in query
    assert 'disease:"Alzheimer\'s disease"' in query or "Alzheimer" in query
    assert 'tissue:"Brain"' in query
    assert 'omics_type:"Proteomics"' in query


def test_asthma_lung_query_builds_proteomexchange_facet_search():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_proteomexchange_api_query(
        strategy="strict",
        search_term="asthma Proteomics lung",
        concept_mappings=mappings,
        interpreted=interpreted,
        query=ASTHMA_QUERY,
    )

    assert 'disease:"asthma"' in query
    assert 'tissue:"Lung"' in query
    assert 'omics_type:"Proteomics"' in query


def test_breast_cancer_query_interprets_disease_and_tissue():
    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    assert interpreted.disease == "breast cancer"
    assert interpreted.tissue == "breast"
    tissue = next(mapping for mapping in mappings if mapping.slot == "tissue")
    assert tissue.curie == "UBERON:0000310"


def test_breast_cancer_query_builds_proteomexchange_facet_search():
    interpreted = interpret_dataset_query(BREAST_CANCER_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_proteomexchange_api_query(
        strategy="strict",
        search_term="breast cancer Proteomics breast",
        concept_mappings=mappings,
        interpreted=interpreted,
        query=BREAST_CANCER_QUERY,
    )

    assert 'disease:"Breast cancer"' in query or 'disease:"breast cancer"' in query.lower()
    assert 'omics_type:"Proteomics"' in query
    assert 'tissue:"Breast"' in query


def test_fetch_proteomexchange_repository_records_for_breast_cancer_query():
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

    with patch("tools.proteomexchange_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        with patch("tools.proteomexchange_dataset_search._fetch_dataset_detail", return_value=None):
            result = fetch_proteomexchange_repository_records(
                mappings,
                max_results=5,
                query=BREAST_CANCER_QUERY,
                interpreted_query=interpreted,
            )

    assert result["repository"] == "ProteomeXchange"
    assert result["records"]
    assert result["records"][0]["accession"] == "PXD016061"
    first_query = mock_get.call_args_list[0].kwargs["params"]["query"]
    assert "Proteomics" in first_query
    assert "repository:pride" in first_query
