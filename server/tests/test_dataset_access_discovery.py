"""Tests for lightweight dataset access discovery."""

from unittest.mock import patch

from domain.dataset_access_discovery import (
    discover_geo_access,
    discover_gxa_access,
    enrich_candidate_with_access,
    enrich_candidates_with_access,
)
from domain.dataset_context_export import export_dataset_search_json
from domain.dataset_search import DatasetCandidate, DatasetSearchResult, InterpretedQuery


def _geo_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "GEO",
        "accession": "GSE32560",
        "title": "Example GEO study",
        "description": "Summary text",
        "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE32560",
        "score": 12.5,
        "metadata_fields": {
            "geo_ftplink": "ftp://ftp.ncbi.nlm.nih.gov/geo/series/GSE32nnn/GSE32560/",
            "geo_suppfile": "CEL",
            "geo_bioproject": "PRJNA147113",
        },
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def _gxa_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "Expression Atlas",
        "accession": "E-MTAB-7860",
        "title": "Example Atlas experiment",
        "description": "RNA-seq study",
        "url": "https://www.ebi.ac.uk/gxa/experiments/E-MTAB-7860",
        "score": 11.0,
        "metadata_fields": {
            "gxa_urls_json": (
                '{"main_page": "experiments/E-MTAB-7860", '
                '"download": "experiments-content/E-MTAB-7860/download/test", '
                '"genome_browsers": "experiments/E-MTAB-7860/redirect/genome-browsers"}'
            ),
        },
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_discover_geo_access_includes_repository_ftp_and_processed_links():
    summary, references = discover_geo_access(_geo_candidate())
    ref_ids = {ref.id for ref in references}

    assert summary.repository_page_url.endswith("acc=GSE32560")
    assert summary.direct_downloads_available is True
    assert summary.auth_may_be_required is False
    assert summary.reference_count == len(references)
    assert f"{_geo_candidate().accession}-repository-page" in ref_ids
    assert f"{_geo_candidate().accession}-ftp-series" in ref_ids
    assert f"{_geo_candidate().accession}-series-matrix" in ref_ids
    assert f"{_geo_candidate().accession}-bioproject" in ref_ids
    assert any(ref.access_type == "ftp" for ref in references)
    assert any(ref.access_type == "direct_download" for ref in references)
    assert any(ref.access_type == "api" for ref in references)


def test_discover_geo_access_derives_ftp_folder_without_esummary_ftplink():
    candidate = _geo_candidate(
        metadata_fields={"geo_suppfile": "CEL"},
    )
    _, references = discover_geo_access(candidate)
    ftp_ref = next(ref for ref in references if ref.access_type == "ftp")
    assert ftp_ref.url == "ftp://ftp.ncbi.nlm.nih.gov/geo/series/GSE32nnn/GSE32560/"


def test_discover_gxa_access_uses_stored_urls_without_fetch():
    summary, references = discover_gxa_access(_gxa_candidate())
    ref_types = {ref.access_type for ref in references}

    assert summary.repository_page_url.endswith("experiments/E-MTAB-7860")
    assert summary.direct_downloads_available is True
    assert "repository_page" in ref_types
    assert "direct_download" in ref_types
    assert "api" in ref_types
    assert any("download" in ref.url for ref in references if ref.access_type == "direct_download")


def test_discover_gxa_access_fetches_detail_when_urls_missing():
    candidate = _gxa_candidate(metadata_fields={})
    detail = {
        "experiment": {
            "accession": "E-MTAB-7860",
            "urls": {
                "main_page": "experiments/E-MTAB-7860",
                "download": "experiments-content/E-MTAB-7860/download/test",
            },
        }
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return detail

    with patch(
        "domain.dataset_access_discovery.requests.get",
        return_value=FakeResponse(),
    ) as mock_get:
        summary, references = discover_gxa_access(candidate)

    mock_get.assert_called_once()
    assert summary.reference_count == len(references)
    assert any(ref.access_type == "direct_download" for ref in references)


def test_enrich_candidates_with_access_attaches_fields():
    enriched = enrich_candidates_with_access([_geo_candidate(), _gxa_candidate()])
    assert all(candidate.access_summary for candidate in enriched)
    assert all(candidate.access_references for candidate in enriched)


def test_enrich_candidate_with_access_is_idempotent_shape():
    candidate = enrich_candidate_with_access(_geo_candidate())
    assert candidate.access_summary is not None
    assert candidate.access_summary.text
    assert candidate.access_references[0].notes


def test_context_export_includes_access_fields():
    candidate = enrich_candidate_with_access(_geo_candidate())
    result = DatasetSearchResult(
        query="test",
        interpreted_query=InterpretedQuery(),
        candidates=[candidate],
    )
    exported = export_dataset_search_json(result)
    payload = exported["candidates"][0]

    assert "access_summary" in payload
    assert payload["access_summary"]["repository_page_url"]
    assert payload["access_references"]
    assert payload["access_references"][0]["access_type"]
