"""Tests for Vivli dataset search connector."""

from unittest.mock import patch

from tools.vivli_dataset_search import (
    _build_vivli_api_query,
    fetch_vivli_repository_records,
    normalize_vivli_record,
    search_vivli_datasets,
)

VIVLI_SEARCH_RESPONSE = {
    "total": 2,
    "hits": [
        {
            "name": "Dataset from Asthma SMARTASIA trial",
            "nctid": "NCT00939341",
            "identifier": ["NCT00939341"],
            "description": "Symbicort maintenance and reliever therapy in asthma patients.",
            "healthCondition": [
                {
                    "name": "asthma",
                    "inDefinedTermSet": "MONDO",
                    "identifier": "0004979",
                }
            ],
            "sample": {
                "sampleType": {"name": "Study Subject"},
                "sampleQuantity": {"value": 862, "unitText": "enrolled subjects"},
            },
            "measurementTechnique": [
                {"name": "Randomized Clinical Trial"},
            ],
            "conditionsOfAccess": "Restricted",
            "includedInDataCatalog": {
                "name": "Vivli",
                "url": "https://vivli.org/",
                "archivedAt": "https://doi.org/10.25934/PR00010978",
            },
            "url": "https://doi.org/10.25934/PR00010978",
        },
        {
            "name": "Dataset from Other asthma study",
            "nctid": "NCT00000001",
            "identifier": ["NCT00000001"],
            "healthCondition": [{"name": "asthma"}],
            "includedInDataCatalog": {"name": "Vivli"},
            "url": "https://doi.org/10.25934/PR00000001",
        },
    ],
}


def _mock_get(url, *args, **kwargs):
    params = kwargs.get("params") or {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            size = int(params.get("size", 0))
            hits = VIVLI_SEARCH_RESPONSE["hits"] if size > 0 else []
            return {
                "total": VIVLI_SEARCH_RESPONSE["total"],
                "hits": hits,
            }

    return FakeResponse()


def test_build_vivli_api_query_uses_catalog_scope_and_health_condition():
    query = _build_vivli_api_query(
        strategy="strict",
        search_term="asthma Randomized Clinical Trial Study Subject",
        concept_mappings=[],
        interpreted={
            "disease": "asthma",
            "assay": "Randomized Clinical Trial",
            "tissue": "Study Subject",
        },
    )

    assert 'includedInDataCatalog.name:"Vivli"' in query
    assert 'healthCondition.name:"asthma"' in query
    assert "Randomized Clinical Trial" in query


def test_search_vivli_datasets_returns_parsed_results():
    with patch("tools.vivli_dataset_search.requests.get", side_effect=_mock_get):
        result = search_vivli_datasets("asthma clinical trial datasets", max_results=5)

    assert result["total_found"] == 2
    assert len(result["results"]) == 2
    accessions = {item["accession"] for item in result["results"]}
    assert "NCT00939341" in accessions
    assert result["source"] == "Vivli / AccessClinicalData@NIAID"


def test_normalize_vivli_record_populates_candidate_fields():
    record = {
        "accession": "NCT00939341",
        "title": "Asthma SMARTASIA trial",
        "description": "Symbicort maintenance and reliever therapy in asthma patients.",
        "summary": "Symbicort maintenance and reliever therapy in asthma patients. asthma",
        "condition_or_disease": "asthma",
        "biosample_type": "Study Subject",
        "assay_method": "Randomized Clinical Trial",
        "species": "Homo sapiens",
        "url": "https://doi.org/10.25934/PR00010978",
        "sample_count": 862,
        "conditions_of_access": "Restricted",
        "data_catalog": "Vivli",
    }

    candidate = normalize_vivli_record(record)

    assert candidate is not None
    assert candidate.repository == "Vivli"
    assert candidate.observed_disease == "asthma"
    assert candidate.metadata_fields["condition_or_disease"] == "asthma"
    assert candidate.source_metadata["access_profile"] == "controlled_or_request_based"


def test_fetch_vivli_repository_records_uses_multi_strategy_search():
    with patch("tools.vivli_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        result = fetch_vivli_repository_records(
            [],
            max_results=5,
            query="Find clinical trial datasets for asthma",
            interpreted_query={
                "disease": "asthma",
                "assay": "Randomized Clinical Trial",
                "tissue": "Study Subject",
            },
        )

    assert result["repository"] == "Vivli"
    assert result["records"]
    assert result["search_strategies"]
    assert mock_get.call_count >= 1
    first_query = mock_get.call_args_list[0].kwargs["params"]["q"]
    assert 'healthCondition.name:"asthma"' in first_query
