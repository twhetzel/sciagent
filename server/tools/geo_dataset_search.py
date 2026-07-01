"""GEO dataset search via NCBI E-utilities (db=gds)."""

from __future__ import annotations

import os
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import collect_metadata_fields
from domain.ontology_grounding import build_geo_search_term

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
GEO_REPOSITORY = "GEO"


def _ncbi_params() -> dict[str, str]:
    return {
        "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
        "email": os.getenv("PUBMED_EMAIL", ""),
    }


def _parse_sample_count(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).split()[0])
    except (TypeError, ValueError):
        return None


def _geo_url(accession: str) -> str:
    if accession.upper().startswith("GSE"):
        return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession.upper()}"
    return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"


def _sample_titles(record: dict[str, Any]) -> list[str]:
    samples = record.get("samples") or record.get("Samples") or []
    if not isinstance(samples, list):
        return []
    titles: list[str] = []
    for sample in samples:
        if isinstance(sample, dict):
            title = sample.get("title") or sample.get("Title")
            if title:
                titles.append(str(title))
    return titles


def normalize_geo_record(record: dict[str, Any]) -> DatasetCandidate | None:
    """Convert one GEO esummary record into a shared DatasetCandidate."""
    accession = (
        record.get("accession")
        or record.get("Accession")
        or record.get("gds")
        or ""
    )
    if not accession:
        return None

    title = str(record.get("title") or record.get("Title") or "Untitled dataset").strip()
    description = str(
        record.get("summary")
        or record.get("Summary")
        or record.get("description")
        or record.get("Description")
        or ""
    ).strip()
    sample_count = _parse_sample_count(record.get("n_samples") or record.get("samples"))
    metadata_fields = collect_metadata_fields(
        title=title,
        description=description,
        taxon=record.get("taxon") or record.get("Taxon") or record.get("organism"),
        gdstype=record.get("gdstype") or record.get("GDSType"),
        platformtitle=record.get("platformtitle"),
        platformtaxa=record.get("platformtaxa") or record.get("samplestaxa"),
        ptechtype=record.get("ptechtype"),
        sample_titles=_sample_titles(record),
    )

    return DatasetCandidate(
        repository=GEO_REPOSITORY,
        accession=str(accession).upper(),
        title=title,
        description=description,
        sample_count=sample_count,
        url=_geo_url(str(accession)),
        metadata_fields=metadata_fields,
    )


def normalize_geo_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    """Normalize Records: map GEO-specific payloads to shared DatasetCandidate models."""
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_geo_record(record)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_geo_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int = 15,
) -> dict[str, Any]:
    """
    Search Repository: query GEO and return raw esummary records.

    Record normalization into DatasetCandidate happens in normalize_geo_records().
    """
    search_term = build_geo_search_term(concept_mappings)
    if not search_term:
        return {
            "search_term": "",
            "total_found": 0,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "error": "No grounded concepts available for GEO search",
        }

    try:
        search_response = requests.get(
            f"{NCBI_BASE}esearch.fcgi",
            params={
                "db": "gds",
                "term": search_term,
                "retmax": max_results,
                "retmode": "json",
                **_ncbi_params(),
            },
            timeout=15,
        )
        search_response.raise_for_status()
        search_data = search_response.json()
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        total_found = int(search_data.get("esearchresult", {}).get("count", 0))

        if not id_list:
            return {
                "search_term": search_term,
                "total_found": total_found,
                "records": [],
                "source": "NCBI GEO",
                "repository": GEO_REPOSITORY,
                "message": "No GEO datasets matched the grounded search",
            }

        summary_response = requests.get(
            f"{NCBI_BASE}esummary.fcgi",
            params={
                "db": "gds",
                "id": ",".join(id_list),
                "retmode": "json",
                **_ncbi_params(),
            },
            timeout=15,
        )
        summary_response.raise_for_status()
        summary_data = summary_response.json()
        result_block = summary_data.get("result", {})

        records: list[dict[str, Any]] = []
        for uid in id_list:
            record = result_block.get(uid, {})
            if isinstance(record, dict):
                records.append(record)

        return {
            "search_term": search_term,
            "total_found": total_found,
            "records": records,
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
        }

    except requests.exceptions.RequestException as exc:
        return {
            "search_term": search_term,
            "total_found": 0,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "error": f"Network error searching GEO: {exc}",
        }
    except Exception as exc:
        return {
            "search_term": search_term,
            "total_found": 0,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "error": f"Error searching GEO: {exc}",
        }


def search_geo_datasets(
    concept_mappings: list[ConceptMapping],
    max_results: int = 15,
) -> dict[str, Any]:
    """Tool entry point: search GEO and return normalized DatasetCandidate records."""
    search_result = fetch_geo_repository_records(concept_mappings, max_results=max_results)
    candidates = normalize_geo_records(search_result.get("records", []))
    return {
        **search_result,
        "candidates": candidates,
    }
