"""GEO dataset search via NCBI E-utilities (db=gds)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import collect_metadata_fields
from domain.ontology_grounding import (
    STRATEGY_PRIORITY,
    build_geo_search_queries,
)

logger = logging.getLogger(__name__)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
GEO_REPOSITORY = "GEO"
NCBI_REQUEST_INTERVAL_SEC = 0.34
_last_ncbi_request_at = 0.0


def _ncbi_params() -> dict[str, str]:
    return {
        "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
        "email": os.getenv("PUBMED_EMAIL", ""),
    }


def _throttle_ncbi_request() -> None:
    global _last_ncbi_request_at
    elapsed = time.monotonic() - _last_ncbi_request_at
    if elapsed < NCBI_REQUEST_INTERVAL_SEC:
        time.sleep(NCBI_REQUEST_INTERVAL_SEC - elapsed)
    _last_ncbi_request_at = time.monotonic()


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
    _throttle_ncbi_request()
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

    records: list[dict[str, Any]] = []
    chunk_size = 100
    for start in range(0, len(id_list), chunk_size):
        chunk = id_list[start : start + chunk_size]
        _throttle_ncbi_request()
        summary_response = requests.get(
            f"{NCBI_BASE}esummary.fcgi",
            params={
                "db": "gds",
                "id": ",".join(chunk),
                "retmode": "json",
                **_ncbi_params(),
            },
            timeout=15,
        )
        summary_response.raise_for_status()
        summary_data = summary_response.json()
        result_block = summary_data.get("result", {})

        for uid in chunk:
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

    esearch runs per strategy; esummary runs once for merged IDs to respect NCBI limits.
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
    strategy_summaries: list[dict[str, str | int]] = []
    max_total_found = 0
    primary_search_term = search_queries[0][1]
    id_to_provenance: dict[str, tuple[str, str]] = {}
    ordered_ids: list[str] = []
    errors: list[str] = []

    for strategy, search_term in search_queries:
        if len(ordered_ids) >= max_results:
            break
        try:
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

            for uid in id_list:
                if uid in id_to_provenance:
                    existing_strategy = id_to_provenance[uid][0]
                    existing_priority = STRATEGY_PRIORITY.get(existing_strategy, 99)
                    new_priority = STRATEGY_PRIORITY.get(strategy, 99)
                    if new_priority < existing_priority:
                        id_to_provenance[uid] = (strategy, search_term)
                    continue

                id_to_provenance[uid] = (strategy, search_term)
                ordered_ids.append(uid)
                if len(ordered_ids) >= max_results:
                    break
        except requests.exceptions.RequestException as exc:
            logger.warning("GEO esearch failed for strategy %s: %s", strategy, exc)
            errors.append(f"{strategy} esearch: {exc}")
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": 0,
                    "retrieved": 0,
                }
            )

    if not ordered_ids:
        payload: dict[str, Any] = {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
            "total_found": max_total_found,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "message": "No GEO datasets matched the grounded search strategies",
        }
        if errors:
            payload["error"] = "; ".join(errors)
        return payload

    try:
        summary_records = _geo_esummary(ordered_ids[:max_results])
    except requests.exceptions.RequestException as exc:
        logger.warning("GEO esummary failed: %s", exc)
        payload = {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
            "total_found": max_total_found,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "error": f"GEO record fetch failed after search succeeded: {exc}",
        }
        if errors:
            payload["error"] = f"{payload['error']}; {'; '.join(errors)}"
        return payload

    records: list[dict[str, Any]] = []
    for record in summary_records:
        uid = str(record.get("uid", ""))
        strategy, search_term = id_to_provenance.get(uid, ("unknown", primary_search_term))
        enriched = dict(record)
        enriched["_retrieval_strategy"] = strategy
        enriched["_retrieval_search_term"] = search_term
        records.append(enriched)

    payload = {
        "search_term": primary_search_term,
        "search_strategies": strategy_summaries,
        "total_found": max_total_found,
        "records": records[:max_results],
        "source": "NCBI GEO",
        "repository": GEO_REPOSITORY,
    }
    if errors:
        payload["warning"] = "; ".join(errors)
    return payload


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
