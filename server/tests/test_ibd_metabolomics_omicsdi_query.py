"""Integration-style test for IBD serum metabolomics OmicsDI query interpretation and search params."""

from unittest.mock import patch

from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from tools.omicsdi_dataset_search import _build_omicsdi_api_query, fetch_omicsdi_repository_records

IBD_METABOLOMICS_QUERY = (
    "Find public metabolomics datasets for inflammatory bowel disease serum."
)


def test_ibd_metabolomics_query_interprets_all_facets():
    interpreted = interpret_dataset_query(IBD_METABOLOMICS_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    assert interpreted.disease == "inflammatory bowel disease"
    assert interpreted.tissue == "serum"
    assert interpreted.assay == "metabolomics"

    disease = next(mapping for mapping in mappings if mapping.slot == "disease")
    tissue = next(mapping for mapping in mappings if mapping.slot == "tissue")
    assay = next(mapping for mapping in mappings if mapping.slot == "assay")

    assert disease.curie == "MONDO:0005265"
    assert tissue.curie == "UBERON:0001977"
    assert assay.curie == "OBI:0003782"


def test_ibd_metabolomics_query_builds_omicsdi_facet_search():
    interpreted = interpret_dataset_query(IBD_METABOLOMICS_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    query = _build_omicsdi_api_query(
        strategy="strict",
        search_term="inflammatory bowel disease Metabolomics serum",
        concept_mappings=mappings,
        interpreted=interpreted,
        query=IBD_METABOLOMICS_QUERY,
    )

    assert 'disease:"inflammatory bowel disease"' in query
    assert 'omics_type:"Metabolomics"' in query
    assert 'tissue:"Serum"' in query


def test_fetch_omicsdi_repository_records_for_ibd_metabolomics_query():
    response = {
        "count": 1,
        "datasets": [
            {
                "id": "ST000923",
                "source": "metabolomics_workbench",
                "title": "Serum metabolomics in inflammatory bowel disease",
                "description": "Untargeted metabolomics of serum from IBD patients.",
                "keywords": ["Inflammatory bowel disease"],
                "organisms": [{"name": "Homo sapiens (Human)"}],
                "omicsType": ["Metabolomics"],
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

    interpreted = interpret_dataset_query(IBD_METABOLOMICS_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    with patch("tools.omicsdi_dataset_search.requests.get", side_effect=_mock_get) as mock_get:
        with patch("tools.omicsdi_dataset_search._fetch_dataset_detail", return_value=None):
            result = fetch_omicsdi_repository_records(
                mappings,
                max_results=5,
                query=IBD_METABOLOMICS_QUERY,
                interpreted_query=interpreted,
            )

    assert result["repository"] == "OmicsDI"
    assert result["records"]
    assert result["records"][0]["accession"] == "ST000923"
    first_query = mock_get.call_args_list[0].kwargs["params"]["query"]
    assert "Metabolomics" in first_query
    assert 'tissue:"Serum"' in first_query
