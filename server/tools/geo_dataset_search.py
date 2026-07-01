"""GEO dataset search via NCBI E-utilities (db=gds)."""

from __future__ import annotations

import os
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import collect_metadata_fields
from domain.ontology_grounding import (
    STRATEGY_PRIORITY,
    build_geo_search_queries,
)

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


def _record_accession(record: dict[str, Any]) -> str:
    accession = (
        record.get("accession")
        or record.get("Accession")
        or record.get("gds")
        or ""
    )
    return str(accession).upper()


def normalize_geo_record(
    record: dict[str, Any],
    *,
    retrieval_strategy: str | None = None,
    retrieval_search_term: str | None = None,
) -> DatasetCandidate | None:
    """Convert one GEO esummary record into a shared DatasetCandidate."""
    accession = _record_accession(record)
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
        accession=accession,
        title=title,
        description=description,
        sample_count=sample_count,
        url=_geo_url(accession),
        metadata_fields=metadata_fields,
        retrieval_strategy=retrieval_strategy,
        retrieval_search_term=retrieval_search_term,
    )


def normalize_geo_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    """Normalize Records: map GEO-specific payloads to shared DatasetCandidate models."""
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_geo_record(
            record,
            retrieval_strategy=record.get("_retrieval_strategy"),
            retrieval_search_term=record.get("_retrieval_search_term"),
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _geo_esearch(search_term: str, max_results: int) -> tuple[list[str], int]:
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
    return id_list, total_found


def _geo_esummary(id_list: list[str]) -> list[dict[str, Any]]:
    if not id_list:
        return []

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
    return records


def fetch_geo_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int = 15,
) -> dict[str, Any]:
    """
    Search Repository: run multi-strategy GEO queries and deduplicate by accession.

    Record normalization into DatasetCandidate happens in normalize_geo_records().
    """
    search_queries = build_geo_search_queries(concept_mappings)
    if not search_queries:
        return {
            "search_term": "",
            "search_strategies": [],
            "total_found": 0,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "error": "No grounded concepts available for GEO search",
        }

    per_strategy_limit = max(5, max_results)
    merged_records: dict[str, dict[str, Any]] = {}
    strategy_summaries: list[dict[str, str | int]] = []
    max_total_found = 0
    primary_search_term = search_queries[0][1]

    try:
        for strategy, search_term in search_queries:
            id_list, total_found = _geo_esearch(search_term, per_strategy_limit)
            max_total_found = max(max_total_found, total_found)
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": total_found,
                    "retrieved": len(id_list),
                }
            )

            for record in _geo_esummary(id_list):
                accession = _record_accession(record)
                if not accession:
                    continue

                enriched = dict(record)
                enriched["_retrieval_strategy"] = strategy
                enriched["_retrieval_search_term"] = search_term

                existing = merged_records.get(accession)
                if existing is None:
                    merged_records[accession] = enriched
                    continue

                existing_priority = STRATEGY_PRIORITY.get(
                    existing.get("_retrieval_strategy", ""), 99
                )
                new_priority = STRATEGY_PRIORITY.get(strategy, 99)
                if new_priority < existing_priority:
                    merged_records[accession] = enriched

        records = list(merged_records.values())
        if not records:
            return {
                "search_term": primary_search_term,
                "search_strategies": strategy_summaries,
                "total_found": max_total_found,
                "records": [],
                "source": "NCBI GEO",
                "repository": GEO_REPOSITORY,
                "message": "No GEO datasets matched the grounded search strategies",
            }

        return {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
            "total_found": max_total_found,
            "records": records[:max_results],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
        }

    except requests.exceptions.RequestException as exc:
        return {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
            "total_found": 0,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "error": f"Network error searching GEO: {exc}",
        }
    except Exception as exc:
        return {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
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
