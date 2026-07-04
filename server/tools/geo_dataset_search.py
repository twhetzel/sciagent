"""GEO dataset search via NCBI E-utilities (db=gds)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchCursor
from domain.evidence_extraction import collect_metadata_fields
from domain.ontology_grounding import (
    STRATEGY_PRIORITY,
    build_geo_search_queries,
)

logger = logging.getLogger(__name__)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
GEO_REPOSITORY = "GEO"
DEFAULT_GEO_MAX_RESULTS = 15
GEO_MAX_RESULTS_CAP = 200
NCBI_REQUEST_INTERVAL_SEC = 0.34
_last_ncbi_request_at = 0.0


def get_geo_max_results(override: int | None = None) -> int:
    """Resolve GEO retrieval limit from explicit arg, GEO_MAX_RESULTS env, or default."""
    if override is not None:
        return max(1, min(int(override), GEO_MAX_RESULTS_CAP))

    raw = os.getenv("GEO_MAX_RESULTS", str(DEFAULT_GEO_MAX_RESULTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_GEO_MAX_RESULTS
    return max(1, min(value, GEO_MAX_RESULTS_CAP))


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


def _geo_esearch(
    search_term: str,
    retmax: int,
    *,
    retstart: int = 0,
) -> tuple[list[str], int]:
    _throttle_ncbi_request()
    search_response = requests.get(
        f"{NCBI_BASE}esearch.fcgi",
        params={
            "db": "gds",
            "term": search_term,
            "retmax": max(0, retmax),
            "retstart": max(0, retstart),
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


def _count_all_strategies(
    search_queries: list[tuple[str, str]],
) -> tuple[list[dict[str, str | int]], int, int, dict[str, int]]:
    """Run count-only esearch for every strategy."""
    strategy_summaries: list[dict[str, str | int]] = []
    strategy_totals: dict[str, int] = {}
    max_total_found = 0
    primary_total_found = 0

    for index, (strategy, search_term) in enumerate(search_queries):
        try:
            _, total_found = _geo_esearch(search_term, 0)
            strategy_totals[strategy] = total_found
            max_total_found = max(max_total_found, total_found)
            if index == 0:
                primary_total_found = total_found
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": total_found,
                    "retrieved": 0,
                    "new_ids": 0,
                }
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("GEO count esearch failed for strategy %s: %s", strategy, exc)
            strategy_totals[strategy] = 0
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": 0,
                    "retrieved": 0,
                    "new_ids": 0,
                }
            )

    return strategy_summaries, max_total_found, primary_total_found, strategy_totals


def _strategy_has_remaining(
    strategy: str,
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
) -> bool:
    return strategy_offsets.get(strategy, 0) < strategy_totals.get(strategy, 0)


def _compute_has_more(
    search_queries: list[tuple[str, str]],
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
) -> bool:
    return any(
        _strategy_has_remaining(strategy, strategy_offsets, strategy_totals)
        for strategy, _ in search_queries
    )


def _collect_geo_id_batch(
    search_queries: list[tuple[str, str]],
    *,
    batch_size: int,
    per_strategy_page: int,
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
    seen_ids: set[str],
) -> tuple[list[str], dict[str, tuple[str, str]], dict[str, int], list[dict[str, str | int]]]:
    """
    Collect the next batch of unseen GEO IDs using strict-first strategy paging.

    Returns ordered ids, provenance map, updated offsets, and per-strategy batch stats.
    """
    ordered_ids: list[str] = []
    id_to_provenance: dict[str, tuple[str, str]] = {}
    updated_offsets = dict(strategy_offsets)
    batch_stats: list[dict[str, str | int]] = []

    for strategy, search_term in search_queries:
        retrieved = 0
        new_ids = 0
        offset = updated_offsets.get(strategy, 0)
        total_for_strategy = strategy_totals.get(strategy, 0)

        while len(ordered_ids) < batch_size and offset < total_for_strategy:
            remaining_batch = batch_size - len(ordered_ids)
            retmax = min(per_strategy_page, remaining_batch, total_for_strategy - offset)
            if retmax <= 0:
                break

            id_list, total_found = _geo_esearch(search_term, retmax, retstart=offset)
            strategy_totals[strategy] = total_found
            total_for_strategy = total_found
            retrieved += len(id_list)

            if not id_list:
                offset = total_for_strategy
                break

            for uid in id_list:
                if uid in seen_ids:
                    continue
                if uid in id_to_provenance:
                    existing_strategy = id_to_provenance[uid][0]
                    existing_priority = STRATEGY_PRIORITY.get(existing_strategy, 99)
                    new_priority = STRATEGY_PRIORITY.get(strategy, 99)
                    if new_priority < existing_priority:
                        id_to_provenance[uid] = (strategy, search_term)
                    continue

                seen_ids.add(uid)
                id_to_provenance[uid] = (strategy, search_term)
                ordered_ids.append(uid)
                new_ids += 1
                if len(ordered_ids) >= batch_size:
                    break

            offset += len(id_list)
            if len(ordered_ids) >= batch_size:
                break

        updated_offsets[strategy] = offset
        batch_stats.append(
            {
                "strategy": strategy,
                "search_term": search_term,
                "total_found": strategy_totals.get(strategy, 0),
                "retrieved": retrieved,
                "new_ids": new_ids,
            }
        )

        if len(ordered_ids) >= batch_size:
            break

    return ordered_ids, id_to_provenance, updated_offsets, batch_stats


def _enrich_summary_records(
    summary_records: list[dict[str, Any]],
    id_to_provenance: dict[str, tuple[str, str]],
    primary_search_term: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in summary_records:
        uid = str(record.get("uid", ""))
        strategy, search_term = id_to_provenance.get(uid, ("unknown", primary_search_term))
        enriched = dict(record)
        enriched["_retrieval_strategy"] = strategy
        enriched["_retrieval_search_term"] = search_term
        records.append(enriched)
    return records


def _build_cursor(
    *,
    concept_mappings: list[ConceptMapping],
    search_queries: list[tuple[str, str]],
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
    seen_ids: set[str],
    seen_accessions: set[str],
    max_results: int,
    total_found: int,
    primary_total_found: int,
    primary_search_term: str,
    query: str = "",
    interpreted_query: dict[str, Any] | None = None,
) -> DatasetSearchCursor:
    from domain.dataset_search import InterpretedQuery

    interpreted = (
        InterpretedQuery.model_validate(interpreted_query)
        if interpreted_query is not None
        else InterpretedQuery()
    )
    return DatasetSearchCursor(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        strategy_offsets=strategy_offsets,
        strategy_totals=strategy_totals,
        seen_ids=sorted(seen_ids),
        seen_accessions=sorted(seen_accessions),
        total_found=total_found,
        primary_total_found=primary_total_found,
        max_results=max_results,
        search_term=primary_search_term,
        has_more=_compute_has_more(search_queries, strategy_offsets, strategy_totals),
    )


def fetch_geo_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Search Repository: run multi-strategy GEO queries and deduplicate by accession.

    esearch counts run for every strategy; the first ID batch is retrieved and summarized.
    """
    max_results = get_geo_max_results(max_results)
    search_queries = build_geo_search_queries(concept_mappings)
    if not search_queries:
        return {
            "search_term": "",
            "search_strategies": [],
            "total_found": 0,
            "primary_total_found": 0,
            "max_results": max_results,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "has_more": False,
            "load_more_cursor": None,
            "error": "No grounded concepts available for GEO search",
        }

    per_strategy_page = max(5, max_results)
    primary_search_term = search_queries[0][1]
    errors: list[str] = []

    strategy_summaries, max_total_found, primary_total_found, strategy_totals = (
        _count_all_strategies(search_queries)
    )

    seen_ids: set[str] = set()
    seen_accessions: set[str] = set()
    strategy_offsets = {strategy: 0 for strategy, _ in search_queries}

    try:
        ordered_ids, id_to_provenance, strategy_offsets, batch_stats = _collect_geo_id_batch(
            search_queries,
            batch_size=max_results,
            per_strategy_page=per_strategy_page,
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_ids=seen_ids,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("GEO esearch batch failed: %s", exc)
        errors.append(f"esearch batch: {exc}")
        ordered_ids = []
        id_to_provenance = {}
        batch_stats = []

    for summary in strategy_summaries:
        for batch in batch_stats:
            if summary["strategy"] == batch["strategy"]:
                summary["retrieved"] = batch["retrieved"]
                summary["new_ids"] = batch["new_ids"]
                break

    if not ordered_ids:
        cursor = _build_cursor(
            concept_mappings=concept_mappings,
            search_queries=search_queries,
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_ids=seen_ids,
            seen_accessions=seen_accessions,
            max_results=max_results,
            total_found=max_total_found,
            primary_total_found=primary_total_found,
            primary_search_term=primary_search_term,
            query=query,
            interpreted_query=interpreted_query,
        )
        payload: dict[str, Any] = {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
            "total_found": max_total_found,
            "primary_total_found": primary_total_found,
            "max_results": max_results,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "message": "No GEO datasets matched the grounded search strategies",
        }
        if errors:
            payload["error"] = "; ".join(errors)
        return payload

    try:
        summary_records = _geo_esummary(ordered_ids)
    except requests.exceptions.RequestException as exc:
        logger.warning("GEO esummary failed: %s", exc)
        payload = {
            "search_term": primary_search_term,
            "search_strategies": strategy_summaries,
            "total_found": max_total_found,
            "primary_total_found": primary_total_found,
            "max_results": max_results,
            "records": [],
            "source": "NCBI GEO",
            "repository": GEO_REPOSITORY,
            "has_more": _compute_has_more(search_queries, strategy_offsets, strategy_totals),
            "load_more_cursor": None,
            "error": f"GEO record fetch failed after search succeeded: {exc}",
        }
        if errors:
            payload["error"] = f"{payload['error']}; {'; '.join(errors)}"
        return payload

    records = _enrich_summary_records(summary_records, id_to_provenance, primary_search_term)
    for record in records:
        accession = _record_accession(record)
        if accession:
            seen_accessions.add(accession)

    cursor = _build_cursor(
        concept_mappings=concept_mappings,
        search_queries=search_queries,
        strategy_offsets=strategy_offsets,
        strategy_totals=strategy_totals,
        seen_ids=seen_ids,
        seen_accessions=seen_accessions,
        max_results=max_results,
        total_found=max_total_found,
        primary_total_found=primary_total_found,
        primary_search_term=primary_search_term,
        query=query,
        interpreted_query=interpreted_query,
    )

    payload = {
        "search_term": primary_search_term,
        "search_strategies": strategy_summaries,
        "total_found": max_total_found,
        "primary_total_found": primary_total_found,
        "max_results": max_results,
        "records": records[:max_results],
        "source": "NCBI GEO",
        "repository": GEO_REPOSITORY,
        "has_more": cursor.has_more,
        "load_more_cursor": cursor.model_dump(),
    }
    if errors:
        payload["warning"] = "; ".join(errors)
    return payload


def fetch_more_geo_repository_records(cursor: DatasetSearchCursor) -> dict[str, Any]:
    """Retrieve the next GEO batch using a saved load-more cursor."""
    concept_mappings = cursor.concept_mappings
    search_queries = build_geo_search_queries(concept_mappings)
    if not search_queries:
        return {
            "records": [],
            "added_count": 0,
            "has_more": False,
            "load_more_cursor": cursor.model_dump(),
            "error": "No grounded concepts available for GEO search",
        }

    per_strategy_page = max(5, cursor.max_results)
    primary_search_term = cursor.search_term or search_queries[0][1]
    seen_ids = set(cursor.seen_ids)
    seen_accessions = set(cursor.seen_accessions)
    strategy_offsets = dict(cursor.strategy_offsets)
    strategy_totals = dict(cursor.strategy_totals)

    if not cursor.has_more:
        return {
            "records": [],
            "added_count": 0,
            "has_more": False,
            "load_more_cursor": cursor.model_dump(),
            "message": "No additional GEO records remain for this search",
        }

    try:
        ordered_ids, id_to_provenance, strategy_offsets, _batch_stats = _collect_geo_id_batch(
            search_queries,
            batch_size=cursor.max_results,
            per_strategy_page=per_strategy_page,
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_ids=seen_ids,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("GEO load-more esearch failed: %s", exc)
        return {
            "records": [],
            "added_count": 0,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "error": f"GEO load-more search failed: {exc}",
        }

    if not ordered_ids:
        updated_cursor = cursor.model_copy(
            update={
                "strategy_offsets": strategy_offsets,
                "strategy_totals": strategy_totals,
                "seen_ids": sorted(seen_ids),
                "seen_accessions": sorted(seen_accessions),
                "has_more": _compute_has_more(search_queries, strategy_offsets, strategy_totals),
            }
        )
        return {
            "records": [],
            "added_count": 0,
            "has_more": updated_cursor.has_more,
            "load_more_cursor": updated_cursor.model_dump(),
            "message": "No new GEO records were found in the next batch",
        }

    try:
        summary_records = _geo_esummary(ordered_ids)
    except requests.exceptions.RequestException as exc:
        logger.warning("GEO load-more esummary failed: %s", exc)
        return {
            "records": [],
            "added_count": 0,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "error": f"GEO load-more record fetch failed: {exc}",
        }

    records = _enrich_summary_records(summary_records, id_to_provenance, primary_search_term)
    for record in records:
        accession = _record_accession(record)
        if accession:
            seen_accessions.add(accession)

    updated_cursor = cursor.model_copy(
        update={
            "strategy_offsets": strategy_offsets,
            "strategy_totals": strategy_totals,
            "seen_ids": sorted(seen_ids),
            "seen_accessions": sorted(seen_accessions),
            "has_more": _compute_has_more(search_queries, strategy_offsets, strategy_totals),
        }
    )

    return {
        "records": records,
        "added_count": len(records),
        "has_more": updated_cursor.has_more,
        "load_more_cursor": updated_cursor.model_dump(),
        "source": "NCBI GEO",
        "repository": GEO_REPOSITORY,
    }


def search_geo_datasets(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
) -> dict[str, Any]:
    """Tool entry point: search GEO and return normalized DatasetCandidate records."""
    search_result = fetch_geo_repository_records(concept_mappings, max_results=max_results)
    candidates = normalize_geo_records(search_result.get("records", []))
    return {
        **search_result,
        "candidates": candidates,
    }
