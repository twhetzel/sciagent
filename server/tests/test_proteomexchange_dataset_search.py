"""Tests for ProteomeXchange dataset search connector."""

from unittest.mock import patch

from tools.proteomexchange_dataset_search import (
    _build_proteomexchange_api_query,
    fetch_proteomexchange_repository_records,
    normalize_proteomexchange_record,
    search_proteomexchange_datasets,
)

SEARCH_RESPONSE = {
    "count": 2,
    "datasets": [
        {
            "id": "PXD012203",
            "source": "pride",
            "title": "Proteomics of Brain Proteome in Alzheimer Disease",
            "description": "Brain tissue proteomics in Alzheimer disease.",
            "keywords": ["Human brain", "Alzheimer disease"],
            "organisms": [{"acc": "", "name": "Homo sapiens (Human)"}],
            "omicsType": ["Proteomics"],
            "publicationDate": "20190201",
        },
        {
            "id": "GSE12345",
            "source": "geo",
            "title": "RNA-seq study that should be filtered out",
            "description": "Not a ProteomeXchange dataset.",
            "keywords": [],
            "organisms": [{"name": "Homo sapiens"}],
            "omicsType": ["Transcriptomics"],
        },
    ],
}

DETAIL_RESPONSE = {
    "additional": {
        "disease": ["Alzheimer's disease"],
        "tissue": ["Brain"],
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
                datasets = SEARCH_RESPONSE["datasets"] if size > 0 else []
                return {
                    "count": SEARCH_RESPONSE["count"],
                    "datasets": datasets,
                }
            if "/ws/dataset/pride/PXD012203" in url:
                return DETAIL_RESPONSE
            return {}

    return FakeResponse()


def test_build_proteomexchange_api_query_scopes_repositories_and_facets():
    query = _build_proteomexchange_api_query(
        strategy="strict",
        search_term="Alzheimer disease Proteomics Brain",
        concept_mappings=[],
        interpreted={
            "disease": "Alzheimer disease",
            "assay": "Proteomics",
            "tissue": "brain",
        },
    )

    assert "repository:pride" in query
    assert "repository:MassIVE" in query
    assert 'disease:"Alzheimer\'s disease"' in query
    assert 'tissue:"Brain"' in query
    assert 'omics_type:"Proteomics"' in query


def test_search_proteomexchange_datasets_returns_parsed_results():
    with patch("tools.proteomexchange_dataset_search.requests.get", side_effect=_mock_get):
        result = search_proteomexchange_datasets(
            "Find public proteomics datasets for Alzheimer's disease brain tissue",
            max_results=5,
        )

    assert result["total_found"] == 2
    assert len(result["results"]) == 1
    assert result["results"][0]["accession"] == "PXD012203"
    assert result["repository"] == "ProteomeXchange"


def test_normalize_proteomexchange_record_populates_candidate_fields():
    record = {
        "accession": "PXD012203",
        "title": "Proteomics of Brain Proteome in Alzheimer Disease",
        "description": "Brain tissue proteomics in Alzheimer disease.",
        "summary": "Brain tissue proteomics in Alzheimer disease.",
        "condition_or_disease": "Alzheimer's disease",
        "biosample_type": "Brain",
        "assay_method": "Mass Spectrometry, Shotgun proteomics",
        "species": "Homo sapiens (Human)",
        "url": "https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD012203",
        "omics_type": "Proteomics",
        "source_database": "pride",
    }

    candidate = normalize_proteomexchange_record(record)

    assert candidate is not None
    assert candidate.repository == "ProteomeXchange"
    assert candidate.observed_disease == "Alzheimer's disease"
    assert candidate.observed_tissue == "Brain"
    assert candidate.metadata_fields["omicsdi_observed_assay"] == "proteomics"
    assert candidate.source_metadata["access_profile"] == "open"


def test_fetch_proteomexchange_repository_records_uses_multi_strategy_search():
    with patch("tools.proteomexchange_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        result = fetch_proteomexchange_repository_records(
            [],
            max_results=5,
            query="Find public proteomics datasets for asthma lung tissue",
            interpreted_query={
                "disease": "asthma",
                "assay": "Proteomics",
                "tissue": "lung",
            },
        )

    assert result["repository"] == "ProteomeXchange"
    assert result["records"]
    assert result["search_strategies"]
    first_query = mock_get.call_args_list[0].kwargs["params"]["query"]
    assert "repository:pride" in first_query
    assert 'disease:"asthma"' in first_query
    assert 'tissue:"Lung"' in first_query
    assert 'omics_type:"Proteomics"' in first_query
