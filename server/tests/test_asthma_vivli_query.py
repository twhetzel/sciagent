"""Integration-style test for asthma Vivli query interpretation and search params."""

from unittest.mock import patch

from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from tools.vivli_dataset_search import _build_vivli_api_query, fetch_vivli_repository_records


ASTHMA_QUERY = "Find clinical trial datasets for asthma"


def test_asthma_query_builds_health_condition_search():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_vivli_api_query(
        strategy="broad_3",
        search_term="asthma",
        concept_mappings=mappings,
        interpreted=interpreted,
    )

    assert 'healthCondition.name:"asthma"' in query
    assert 'includedInDataCatalog.name:"Vivli"' in query


def test_fetch_vivli_repository_records_for_asthma_query():
    response = {
        "total": 1,
        "hits": [
            {
                "name": "Dataset from Asthma SMARTASIA trial",
                "nctid": "NCT00939341",
                "identifier": ["NCT00939341"],
                "healthCondition": [{"name": "asthma"}],
                "includedInDataCatalog": {"name": "Vivli"},
                "url": "https://doi.org/10.25934/PR00010978",
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
                    "total": response["total"],
                    "hits": response["hits"] if size > 0 else [],
                }

        return FakeResponse()

    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    with patch("tools.vivli_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        result = fetch_vivli_repository_records(
            mappings,
            max_results=5,
            query=ASTHMA_QUERY,
            interpreted_query=interpreted,
        )

    assert result["repository"] == "Vivli"
    assert result["records"]
    assert result["records"][0]["accession"] == "NCT00939341"
    first_query = mock_get.call_args_list[0].kwargs["params"]["q"]
    assert "asthma" in first_query.lower()
