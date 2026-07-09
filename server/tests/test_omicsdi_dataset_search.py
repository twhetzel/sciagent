"""Tests for OmicsDI dataset search connector."""

from unittest.mock import patch

from tools.omicsdi_dataset_search import (
    _build_omicsdi_api_query,
    fetch_omicsdi_repository_records,
    normalize_omicsdi_record,
    search_omicsdi_datasets,
)

OMICSDI_SEARCH_RESPONSE = {
    "count": 2,
    "datasets": [
        {
            "id": "PXD016061",
            "source": "pride",
            "title": "Quantitative proteomic analysis for breast cancer",
            "description": "Proteome data of distant metastatic breast cancer FFPE tissue.",
            "keywords": ["Breast cancer", "Quantitative proteomics"],
            "organisms": [{"acc": "", "name": "Homo sapiens (Human)"}],
            "omicsType": ["Proteomics"],
            "publicationDate": "20200605",
        },
        {
            "id": "PXD000456",
            "source": "pride",
            "title": "Human glomerular extracellular matrix analysed by LC-MSMS",
            "description": "Extracellular matrix proteins were isolated from human glomeruli.",
            "keywords": ["Human", "kidney", "glomerulus"],
            "organisms": [{"acc": "", "name": "Homo sapiens"}],
            "omicsType": ["Proteomics"],
            "publicationDate": "20140122",
        },
    ],
}

DETAIL_RESPONSE = {
    "additional": {
        "disease": ["Breast Cancer"],
        "tissue": ["Breast Cancer Cell Line", "Breast Cancer Cell"],
        "technology_type": ["Mass Spectrometry", "Shotgun proteomics"],
    }
}


def _mock_get(url, *args, **kwargs):
    params = kwargs.get("params") or {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            if "/ws/dataset/search" in url:
                size = int(params.get("size", 0))
                datasets = OMICSDI_SEARCH_RESPONSE["datasets"] if size > 0 else []
                return {
                    "count": OMICSDI_SEARCH_RESPONSE["count"],
                    "datasets": datasets,
                }
            if "/ws/dataset/pride/PXD016061" in url:
                return DETAIL_RESPONSE
            return {}

    return FakeResponse()


def test_build_omicsdi_api_query_uses_disease_tissue_and_omics_type():
    query = _build_omicsdi_api_query(
        strategy="strict",
        search_term="Breast cancer Proteomics Breast",
        concept_mappings=[],
        interpreted={
            "disease": "breast cancer",
            "assay": "Proteomics",
            "tissue": "breast",
        },
    )

    assert 'disease:"Breast cancer"' in query
    assert 'tissue:"Breast"' in query
    assert 'omics_type:"Proteomics"' in query


def test_search_omicsdi_datasets_returns_parsed_results():
    with patch("tools.omicsdi_dataset_search.requests.get", side_effect=_mock_get):
        result = search_omicsdi_datasets(
            "Find public proteomics datasets for breast cancer breast tissue",
            max_results=5,
        )

    assert result["total_found"] == 2
    assert len(result["results"]) == 2
    accessions = {item["accession"] for item in result["results"]}
    assert "PXD016061" in accessions
    assert result["source"] == "OmicsDI API"


def test_normalize_omicsdi_record_populates_candidate_fields():
    record = {
        "accession": "PXD016061",
        "title": "Quantitative proteomic analysis for breast cancer",
        "description": "Proteome data of distant metastatic breast cancer FFPE tissue.",
        "summary": "Proteome data of distant metastatic breast cancer FFPE tissue.",
        "condition_or_disease": "Breast Cancer",
        "biosample_type": "Breast Cancer Cell Line, Breast Cancer Cell",
        "assay_method": "Mass Spectrometry, Shotgun proteomics",
        "species": "Homo sapiens (Human)",
        "url": "https://www.omicsdi.org/dataset/pride/PXD016061",
        "omics_type": "Proteomics",
        "source_database": "pride",
    }

    candidate = normalize_omicsdi_record(record)

    assert candidate is not None
    assert candidate.repository == "OmicsDI"
    assert candidate.observed_disease == "Breast Cancer"
    assert candidate.metadata_fields["condition_or_disease"] == "Breast Cancer"
    assert candidate.metadata_fields["biosample_type"] == "Breast Cancer Cell Line, Breast Cancer Cell"
    assert candidate.metadata_fields["omicsdi_omics_type"] == "Proteomics"
    assert candidate.metadata_fields["omicsdi_observed_assay"] == "proteomics"
    assert candidate.source_metadata["access_profile"] == "mixed"


def test_fetch_omicsdi_repository_records_uses_multi_strategy_search():
    with patch("tools.omicsdi_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        result = fetch_omicsdi_repository_records(
            [],
            max_results=5,
            query="Find public proteomics datasets for breast cancer breast tissue",
            interpreted_query={
                "disease": "breast cancer",
                "assay": "Proteomics",
                "tissue": "breast",
            },
        )

    assert result["repository"] == "OmicsDI"
    assert result["records"]
    assert result["search_strategies"]
    assert mock_get.call_count >= 1
    first_query = mock_get.call_args_list[0].kwargs["params"]["query"]
    assert 'disease:"Breast cancer"' in first_query
