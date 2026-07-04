"""Tests for Expression Atlas multi-strategy search."""

from unittest.mock import patch

from tools.expression_atlas import search_expression_atlas

STRICT_RESPONSE = {
    "hitCount": 1,
    "entries": [
        {
            "id": "E-MTAB-7860",
            "fields": {
                "description": [
                    "RNA-seq of biopsies, crypts and organoids of inflamed and non-inflamed biopsies of ulcerative colitis patients"
                ]
            },
        }
    ],
}

BROAD_RESPONSE = {
    "hitCount": 3,
    "entries": [
        {
            "id": "E-MTAB-7860",
            "fields": {"description": ["RNA-seq UC organoids"]},
        },
        {
            "id": "E-GEOD-57945",
            "fields": {"description": ["RNA-seq pediatric IBD cohort"]},
        },
        {
            "id": "E-GEOD-83687",
            "fields": {"description": ["RNA-seq bowel resection IBD"]},
        },
    ],
}

DETAIL = {
    "experiment": {
        "species": "Homo sapiens",
        "type": "rnaseq_mrna_differential",
        "urls": {"main_page": "experiments/ACCESSION"},
    }
}


def _mock_get(url, *args, **kwargs):
    params = kwargs.get("params") or {}
    query = params.get("query", "")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            if "ebisearch" in url:
                if query == "ulcerative colitis RNA-seq colon":
                    return STRICT_RESPONSE
                if query == "ulcerative colitis RNA-seq":
                    return BROAD_RESPONSE
                return {"hitCount": 0, "entries": []}
            accession = url.rsplit("/", 1)[-1]
            payload = dict(DETAIL)
            payload["experiment"] = dict(DETAIL["experiment"])
            payload["experiment"]["urls"] = {
                "main_page": f"experiments/{accession}",
            }
            return payload

    return FakeResponse()


def test_search_expression_atlas_runs_multi_strategy_with_dedup():
    interpreted = {
        "disease": "ulcerative colitis",
        "tissue": "colon",
        "assay": "RNA-seq",
        "organism": "human",
    }

    with patch("tools.expression_atlas.requests.get", side_effect=_mock_get):
        result = search_expression_atlas(
            "Find public RNA-seq datasets for ulcerative colitis colon tissue",
            max_results=10,
            species="Homo sapiens",
            interpreted_query=interpreted,
        )

    assert len(result["search_strategies"]) >= 2
    assert result["primary_total_found"] == 1
    assert result["total_found"] == 3
    accessions = {item["accession"] for item in result["results"]}
    assert "E-MTAB-7860" in accessions
    assert "E-GEOD-57945" in accessions
    assert result["results"][0]["retrieval_strategy"] == "strict"
