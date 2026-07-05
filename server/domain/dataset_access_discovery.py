"""Lightweight repository access discovery for ranked dataset candidates."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from domain.dataset_search import AccessSummary, DataAccessReference, DatasetCandidate

logger = logging.getLogger(__name__)

GEO_REPOSITORY = "GEO"
GXA_REPOSITORY = "Expression Atlas"
GXA_JSON_BASE = "https://www.ebi.ac.uk/gxa/json/experiments"
GXA_SITE_BASE = "https://www.ebi.ac.uk/gxa"
REQUEST_TIMEOUT = 15

ACCESS_TYPE_REPOSITORY = "repository_page"
ACCESS_TYPE_DIRECT = "direct_download"
ACCESS_TYPE_API = "api"
ACCESS_TYPE_FTP = "ftp"
ACCESS_TYPE_CONTROLLED = "controlled"
ACCESS_TYPE_UNKNOWN = "unknown"


def _reference(
    *,
    ref_id: str,
    label: str,
    url: str = "",
    access_type: str = ACCESS_TYPE_UNKNOWN,
    requires_auth: bool = False,
    notes: str = "",
) -> DataAccessReference:
    return DataAccessReference(
        id=ref_id,
        label=label,
        url=url,
        access_type=access_type,
        requires_auth=requires_auth,
        notes=notes,
    )


def _geo_study_url(accession: str, candidate_url: str = "") -> str:
    if candidate_url:
        return candidate_url
    acc = accession.upper()
    if acc.startswith("GSE"):
        return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}"
    return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"


def _geo_ftp_series_folder(accession: str, ftplink: str | None = None) -> str:
    if ftplink:
        return ftplink.rstrip("/") + "/"
    acc = accession.upper()
    if not acc.startswith("GSE") or len(acc) <= 3:
        return ""
    numeric = acc[3:]
    prefix = f"GSE{numeric[:-3]}nnn" if len(numeric) > 3 else acc
    return f"ftp://ftp.ncbi.nlm.nih.gov/geo/series/{prefix}/{acc}/"


def _geo_esummary_api_url(accession: str) -> str:
    return (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=gds&term={accession}[Accession]&retmode=json"
    )


def discover_geo_access(candidate: DatasetCandidate) -> tuple[AccessSummary, list[DataAccessReference]]:
    """Derive GEO repository, FTP, and standard series file references from metadata."""
    accession = candidate.accession.upper()
    metadata = candidate.metadata_fields
    repository_url = _geo_study_url(accession, candidate.url)
    references: list[DataAccessReference] = []

    references.append(
        _reference(
            ref_id=f"{accession}-repository-page",
            label=f"GEO study page ({accession})",
            url=repository_url,
            access_type=ACCESS_TYPE_REPOSITORY,
            notes="Primary NCBI GEO accession page for study metadata and download options.",
        )
    )

    references.append(
        _reference(
            ref_id=f"{accession}-esummary-api",
            label=f"GEO metadata API ({accession})",
            url=_geo_esummary_api_url(accession),
            access_type=ACCESS_TYPE_API,
            notes="NCBI Entrez E-utilities esummary endpoint for study metadata (no raw data transfer).",
        )
    )

    ftplink = metadata.get("geo_ftplink") or _geo_ftp_series_folder(accession)
    if ftplink:
        base = ftplink.rstrip("/")
        references.append(
            _reference(
                ref_id=f"{accession}-ftp-series",
                label=f"GEO FTP series folder ({accession})",
                url=base + "/",
                access_type=ACCESS_TYPE_FTP,
                notes="FTP directory for series-level processed, supplementary, and metadata files.",
            )
        )
        references.extend(
            [
                _reference(
                    ref_id=f"{accession}-series-matrix",
                    label="Series matrix (processed expression)",
                    url=f"{base}/matrix/{accession}_series_matrix.txt.gz",
                    access_type=ACCESS_TYPE_DIRECT,
                    notes="Standard GEO series matrix file when submitted by authors.",
                ),
                _reference(
                    ref_id=f"{accession}-soft-family",
                    label="SOFT family (sample metadata)",
                    url=f"{base}/soft/{accession}_family.soft.gz",
                    access_type=ACCESS_TYPE_DIRECT,
                    notes="GEO SOFT format family file with sample and platform metadata.",
                ),
                _reference(
                    ref_id=f"{accession}-miniml-family",
                    label="MINiML metadata archive",
                    url=f"{base}/miniml/{accession}_family.xml.tgz",
                    access_type=ACCESS_TYPE_DIRECT,
                    notes="GEO MINiML metadata archive for programmatic access.",
                ),
            ]
        )

    bioproject = metadata.get("geo_bioproject", "").strip()
    if bioproject:
        references.append(
            _reference(
                ref_id=f"{accession}-bioproject",
                label=f"NCBI BioProject ({bioproject})",
                url=f"https://www.ncbi.nlm.nih.gov/bioproject/{bioproject}",
                access_type=ACCESS_TYPE_REPOSITORY,
                notes="Linked BioProject record for associated raw data accessions (e.g. SRA).",
            )
        )

    suppfile = metadata.get("geo_suppfile", "").strip()
    summary_notes: list[str] = []
    if suppfile:
        summary_notes.append(f"GEO reports supplementary file types: {suppfile}.")
    if ftplink:
        summary_notes.append("Standard GEO FTP paths for series matrix, SOFT, and MINiML are listed.")

    direct_available = any(ref.access_type == ACCESS_TYPE_DIRECT for ref in references)
    summary = AccessSummary(
        text=(
            f"{len(references)} access reference(s) for {accession} via NCBI GEO. "
            + (" ".join(summary_notes) if summary_notes else "Repository page and FTP metadata links discovered.")
        ),
        repository_page_url=repository_url,
        reference_count=len(references),
        direct_downloads_available=direct_available,
        auth_may_be_required=False,
    )
    return summary, references


def _gxa_absolute_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{GXA_SITE_BASE}/{path.lstrip('/')}"


def _parse_gxa_urls(metadata: dict[str, str]) -> dict[str, str]:
    raw = metadata.get("gxa_urls_json", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid gxa_urls_json on candidate metadata")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items() if value}


def _fetch_gxa_urls(accession: str) -> dict[str, str]:
    """Fetch lightweight Expression Atlas experiment JSON for URL discovery only."""
    try:
        response = requests.get(
            f"{GXA_JSON_BASE}/{accession}",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        experiment = response.json().get("experiment")
        if isinstance(experiment, dict):
            urls = experiment.get("urls")
            if isinstance(urls, dict):
                return {str(key): str(value) for key, value in urls.items() if value}
    except requests.RequestException as exc:
        logger.warning("Expression Atlas access discovery failed for %s: %s", accession, exc)
    return {}


def discover_gxa_access(candidate: DatasetCandidate) -> tuple[AccessSummary, list[DataAccessReference]]:
    """Derive Expression Atlas repository and download references from stored or fetched URLs."""
    accession = candidate.accession
    repository_url = candidate.url or _gxa_absolute_url(f"experiments/{accession}")
    urls = _parse_gxa_urls(candidate.metadata_fields)
    if not urls:
        urls = _fetch_gxa_urls(accession)

    references: list[DataAccessReference] = []
    main_page = urls.get("main_page")
    if main_page:
        repository_url = _gxa_absolute_url(main_page)

    references.append(
        _reference(
            ref_id=f"{accession}-repository-page",
            label=f"Expression Atlas experiment page ({accession})",
            url=repository_url,
            access_type=ACCESS_TYPE_REPOSITORY,
            notes="Primary Expression Atlas experiment page with metadata and download options.",
        )
    )

    references.append(
        _reference(
            ref_id=f"{accession}-json-api",
            label=f"Expression Atlas JSON API ({accession})",
            url=f"{GXA_JSON_BASE}/{accession}",
            access_type=ACCESS_TYPE_API,
            notes="Lightweight experiment metadata JSON endpoint (no expression matrix download).",
        )
    )

    download_path = urls.get("download")
    if download_path:
        references.append(
            _reference(
                ref_id=f"{accession}-download-page",
                label="Expression Atlas download (processed results)",
                url=_gxa_absolute_url(download_path),
                access_type=ACCESS_TYPE_DIRECT,
                notes="Web endpoint for processed differential expression downloads configured in Atlas.",
            )
        )

    genome_browsers = urls.get("genome_browsers")
    if genome_browsers:
        references.append(
            _reference(
                ref_id=f"{accession}-genome-browser",
                label="Genome browser view",
                url=_gxa_absolute_url(genome_browsers),
                access_type=ACCESS_TYPE_API,
                notes="Expression Atlas genome browser redirect for interactive inspection.",
            )
        )

    direct_available = any(ref.access_type == ACCESS_TYPE_DIRECT for ref in references)
    summary = AccessSummary(
        text=(
            f"{len(references)} access reference(s) for {accession} via Expression Atlas. "
            "Repository page and lightweight API/download links discovered."
        ),
        repository_page_url=repository_url,
        reference_count=len(references),
        direct_downloads_available=direct_available if references else None,
        auth_may_be_required=False,
    )
    return summary, references


def discover_candidate_access(
    candidate: DatasetCandidate,
) -> tuple[AccessSummary, list[DataAccessReference]]:
    """Discover access references for one candidate based on repository."""
    if candidate.repository == GEO_REPOSITORY:
        return discover_geo_access(candidate)
    if candidate.repository == GXA_REPOSITORY:
        return discover_gxa_access(candidate)
    repository_url = candidate.url or ""
    references = [
        _reference(
            ref_id=f"{candidate.accession}-repository-page",
            label=f"Repository page ({candidate.accession})",
            url=repository_url,
            access_type=ACCESS_TYPE_REPOSITORY if repository_url else ACCESS_TYPE_UNKNOWN,
            notes="Repository page link when available.",
        )
    ]
    summary = AccessSummary(
        text=f"Basic repository page reference for {candidate.accession}.",
        repository_page_url=repository_url,
        reference_count=len(references),
        direct_downloads_available=None,
        auth_may_be_required=None,
    )
    return summary, references


def enrich_candidate_with_access(candidate: DatasetCandidate) -> DatasetCandidate:
    """Attach discovered access summary and references to a candidate."""
    summary, references = discover_candidate_access(candidate)
    return candidate.model_copy(
        update={
            "access_summary": summary,
            "access_references": references,
        }
    )


def enrich_candidates_with_access(
    candidates: list[DatasetCandidate],
) -> list[DatasetCandidate]:
    """Discover and attach access metadata for all ranked candidates."""
    return [enrich_candidate_with_access(candidate) for candidate in candidates]


def access_reference_to_dict(reference: DataAccessReference) -> dict[str, Any]:
    """Serialize an access reference for agent context export."""
    return reference.model_dump()
