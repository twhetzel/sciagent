"""Tests for Expression Atlas search tool."""

from unittest.mock import patch

from tools.expression_atlas import search_expression_atlas


SEARCH_RESPONSE = {
    "hitCount": 2,
    "entries": [
        {
            "id": "E-GEOD-14580",
            "source": "atlas-experiments",
            "fields": {
                "id": ["E-GEOD-14580"],
                "description": [
                    "Mucosal gene signatures to predict response to infliximab in patients with ulcerative colitis"
                ],
            },
        },
        {
            "id": "E-MTAB-7860",
            "source": "atlas-experiments",
            "fields": {
                "id": ["E-MTAB-7860"],
                "description": [
                    "RNA-seq of biopsies, crypts and organoids of inflamed and non-inflamed biopsies of ulcerative colitis patients"
                ],
            },
        },
    ],
}

DETAIL_RESPONSES = {
    "E-GEOD-14580": {
        "experiment": {
            "accession": "E-GEOD-14580",
            "type": "microarray_1colour_mrna_differential",
            "description": "Mucosal gene signatures to predict response to infliximab in patients with ulcerative colitis",
            "species": "Homo sapiens",
            "urls": {"main_page": "experiments/E-GEOD-14580"},
        }
    },
    "E-MTAB-7860": {
        "experiment": {
            "accession": "E-MTAB-7860",
            "type": "rnaseq_mrna_differential",
            "description": "RNA-seq of biopsies, crypts and organoids of inflamed and non-inflamed biopsies of ulcerative colitis patients",
            "species": "Homo sapiens",
            "urls": {"main_page": "experiments/E-MTAB-7860"},
        }
    },
}


def _mock_get(url, *args, **kwargs):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            if "ebisearch" in url:
                return SEARCH_RESPONSE
            for accession, payload in DETAIL_RESPONSES.items():
                if accession in url:
                    return payload
            return {}

    return FakeResponse()


def test_search_expression_atlas_returns_enriched_results():
    with patch("tools.expression_atlas.requests.get", side_effect=_mock_get):
        result = search_expression_atlas("ulcerative colitis", max_results=5)

    assert result["total_found"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["accession"] == "E-GEOD-14580"
    assert result["results"][0]["species"] == "Homo sapiens"
    assert "microarray" in result["results"][0]["experiment_type"]
    assert result["results"][0]["url"].startswith("https://www.ebi.ac.uk/gxa/")


def test_search_expression_atlas_filters_by_species():
    with patch("tools.expression_atlas.requests.get", side_effect=_mock_get):
        result = search_expression_atlas("ulcerative colitis", max_results=5, species="human")

    assert len(result["results"]) == 2
    assert all(item["species"] == "Homo sapiens" for item in result["results"])
