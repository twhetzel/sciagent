"""
Expression Atlas tool - search EMBL-EBI Gene Expression Atlas experiments.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate, InterpretedQuery
from domain.evidence_extraction import collect_metadata_fields
from domain.gxa_assay import annotate_gxa_metadata_fields
from domain.facet_search_strategies import (
    STRATEGY_PRIORITY,
    build_facet_search_queries,
)

logger = logging.getLogger(__name__)

EBI_SEARCH_BASE = "https://www.ebi.ac.uk/ebisearch/ws/rest/atlas-experiments"
GXA_JSON_BASE = "https://www.ebi.ac.uk/gxa/json/experiments"
GXA_REPOSITORY = "Expression Atlas"
DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_CAP = 50
REQUEST_TIMEOUT = 15


def get_expression_atlas_max_results(override: int | None = None) -> int:
    """Resolve result limit from explicit arg, env var, or default."""
    if override is not None:
        return max(1, min(int(override), MAX_RESULTS_CAP))

    raw = os.getenv("EXPRESSION_ATLAS_MAX_RESULTS", str(DEFAULT_MAX_RESULTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_RESULTS
    return max(1, min(value, MAX_RESULTS_CAP))


def _field_value(fields: dict[str, Any], name: str) -> str:
    values = fields.get(name) or []
    if values:
        return str(values[0])
    return ""


def _atlas_url(accession: str) -> str:
    return f"https://www.ebi.ac.uk/gxa/experiments/{accession}"


def _species_matches(species: str | None, item_species: str) -> bool:
    if not species:
        return True
    species_lower = species.lower()
    item_lower = (item_species or "").lower()
    if species_lower in {"human", "homo sapiens"}:
        return item_lower == "homo sapiens"
    return species_lower in item_lower


def _fetch_experiment_detail(accession: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{GXA_JSON_BASE}/{accession}",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        experiment = response.json().get("experiment")
        if isinstance(experiment, dict):
            return experiment
    except requests.RequestException as exc:
        logger.warning("Expression Atlas detail fetch failed for %s: %s", accession, exc)
    return None


def _parse_search_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    accession = str(entry.get("id") or "").strip()
    if not accession:
        return None

    fields = entry.get("fields") or {}
    description = _field_value(fields, "description") or accession

    return {
        "accession": accession,
        "title": description,
        "description": description,
        "species": _field_value(fields, "species"),
        "experiment_type": _field_value(fields, "experimenttype"),
        "assay_type": _field_value(fields, "assaytype"),
        "number_of_assays": _field_value(fields, "numberofassays"),
        "url": _atlas_url(accession),
    }


def _enrich_experiment(result: dict[str, Any]) -> dict[str, Any]:
    detail = _fetch_experiment_detail(result["accession"])
    if not detail:
        return result

    enriched = dict(result)
    if detail.get("description"):
        enriched["title"] = detail["description"]
        enriched["description"] = detail["description"]
    if detail.get("species"):
        enriched["species"] = detail["species"]
    if detail.get("type"):
        enriched["experiment_type"] = detail["type"]
    if detail.get("urls", {}).get("main_page"):
        enriched["url"] = f"https://www.ebi.ac.uk/gxa/{detail['urls']['main_page']}"
    urls = detail.get("urls")
    if isinstance(urls, dict) and urls:
        enriched["_gxa_urls"] = urls
    return enriched


def _ebi_atlas_search(search_term: str, size: int) -> tuple[list[dict[str, Any]], int]:
    response = requests.get(
        EBI_SEARCH_BASE,
        params={
            "query": search_term,
            "format": "json",
            "size": max(0, size),
            "fields": "id,description,species,experimenttype,assaytype,numberofassays",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("entries") or [], int(data.get("hitCount", 0))


def _resolve_search_queries(
    *,
    query: str,
    interpreted_query: InterpretedQuery | dict[str, Any] | None = None,
    concept_mappings: list[ConceptMapping] | None = None,
) -> list[tuple[str, str]]:
    interpreted = None
    if interpreted_query is not None:
        interpreted = (
            InterpretedQuery.model_validate(interpreted_query)
            if isinstance(interpreted_query, dict)
            else interpreted_query
        )

    facet_queries = build_facet_search_queries(
        interpreted=interpreted,
        concept_mappings=concept_mappings,
    )
    if facet_queries:
        return facet_queries
    if query.strip():
        return [("adhoc", query)]
    return []


def _run_multi_strategy_search(
    search_queries: list[tuple[str, str]],
    *,
    max_results: int,
    species: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str | int]], int, int, list[str]]:
    strategy_summaries: list[dict[str, str | int]] = []
    accession_to_record: dict[str, dict[str, Any]] = {}
    accession_priority: dict[str, int] = {}
    max_total_found = 0
    primary_total_found = 0
    errors: list[str] = []

    for index, (strategy, search_term) in enumerate(search_queries):
        retrieved = 0
        new_ids = 0
        hit_count = 0

        try:
            entries, hit_count = _ebi_atlas_search(search_term, max_results)
        except requests.exceptions.RequestException as exc:
            logger.warning("Expression Atlas search failed for strategy %s: %s", strategy, exc)
            errors.append(f"{strategy}: {exc}")
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": 0,
                    "retrieved": 0,
                    "new_ids": 0,
                }
            )
            continue

        max_total_found = max(max_total_found, hit_count)
        if index == 0:
            primary_total_found = hit_count

        for entry in entries:
            parsed = _parse_search_entry(entry)
            if not parsed:
                continue
            retrieved += 1
            enriched = _enrich_experiment(parsed)
            if not _species_matches(species, enriched.get("species", "")):
                continue

            accession = enriched["accession"]
            priority = STRATEGY_PRIORITY.get(strategy, 99)
            existing_priority = accession_priority.get(accession)
            if existing_priority is not None:
                if priority < existing_priority:
                    enriched["_retrieval_strategy"] = strategy
                    enriched["_retrieval_search_term"] = search_term
                    accession_to_record[accession] = enriched
                    accession_priority[accession] = priority
                continue

            enriched["_retrieval_strategy"] = strategy
            enriched["_retrieval_search_term"] = search_term
            accession_to_record[accession] = enriched
            accession_priority[accession] = priority
            new_ids += 1

            if len(accession_to_record) >= max_results:
                break

        strategy_summaries.append(
            {
                "strategy": strategy,
                "search_term": search_term,
                "total_found": hit_count,
                "retrieved": retrieved,
                "new_ids": new_ids,
            }
        )

        if len(accession_to_record) >= max_results:
            break

    records = sorted(
        accession_to_record.values(),
        key=lambda item: (
            STRATEGY_PRIORITY.get(item.get("_retrieval_strategy"), 99),
            item.get("accession", ""),
        ),
    )[:max_results]
    return records, strategy_summaries, max_total_found, primary_total_found, errors


def normalize_gxa_record(
    record: dict[str, Any],
    *,
    retrieval_strategy: str | None = None,
    retrieval_search_term: str | None = None,
) -> DatasetCandidate | None:
    """Convert one Expression Atlas record into a shared DatasetCandidate."""
    accession = str(record.get("accession") or "").strip()
    if not accession:
        return None

    title = str(record.get("title") or "Untitled experiment").strip()
    description = str(record.get("description") or "").strip()
    sample_count_raw = record.get("number_of_assays")
    sample_count = None
    if sample_count_raw not in (None, ""):
        try:
            sample_count = int(str(sample_count_raw).split()[0])
        except (TypeError, ValueError):
            sample_count = None

    experiment_type = str(record.get("experiment_type") or record.get("assay_type") or "").strip()
    metadata_fields = collect_metadata_fields(
        title=title,
        description=description,
        taxon=record.get("species"),
        gdstype=experiment_type,
    )
    metadata_fields = annotate_gxa_metadata_fields(
        metadata_fields,
        experiment_type=experiment_type,
        assay_type=str(record.get("assay_type") or ""),
    )
    gxa_urls = record.get("_gxa_urls")
    if isinstance(gxa_urls, dict) and gxa_urls:
        metadata_fields["gxa_urls_json"] = json.dumps(gxa_urls)

    return DatasetCandidate(
        repository=GXA_REPOSITORY,
        accession=accession,
        title=title,
        description=description,
        sample_count=sample_count,
        url=str(record.get("url") or _atlas_url(accession)),
        metadata_fields=metadata_fields,
        retrieval_strategy=retrieval_strategy or record.get("_retrieval_strategy"),
        retrieval_search_term=retrieval_search_term or record.get("_retrieval_search_term"),
    )


def normalize_gxa_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    """Normalize Records: map GXA payloads to shared DatasetCandidate models."""
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_gxa_record(record)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_gxa_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    species: str | None = None,
) -> dict[str, Any]:
    """Search Repository: multi-strategy Expression Atlas search with deduplication."""
    max_results = get_expression_atlas_max_results(max_results)
    search_queries = _resolve_search_queries(
        query=query,
        interpreted_query=interpreted_query,
        concept_mappings=concept_mappings,
    )

    if not search_queries:
        return {
            "search_term": "",
            "search_strategies": [],
            "total_found": 0,
            "primary_total_found": 0,
            "max_results": max_results,
            "records": [],
            "source": "Expression Atlas",
            "repository": GXA_REPOSITORY,
            "has_more": False,
            "load_more_cursor": None,
            "error": "No grounded concepts available for Expression Atlas search",
        }

    records, strategy_summaries, max_total_found, primary_total_found, errors = (
        _run_multi_strategy_search(
            search_queries,
            max_results=max_results,
            species=species,
        )
    )

    payload: dict[str, Any] = {
        "search_term": search_queries[0][1],
        "search_strategies": strategy_summaries,
        "total_found": max_total_found,
        "primary_total_found": primary_total_found,
        "max_results": max_results,
        "records": records,
        "source": "Expression Atlas",
        "repository": GXA_REPOSITORY,
        "has_more": False,
        "load_more_cursor": None,
    }
    if not records:
        payload["message"] = "No Expression Atlas experiments matched the grounded search strategies"
    if errors:
        payload["warning"] = "; ".join(errors)
    return payload


def search_expression_atlas(
    query: str,
    max_results: int | None = None,
    species: str | None = None,
    *,
    interpreted_query: dict[str, Any] | InterpretedQuery | None = None,
) -> dict[str, Any]:
    """
    Search EMBL-EBI Expression Atlas for matching experiments.

    When ``interpreted_query`` is provided, runs the same multi-strategy facet
    search used by GEO (strict -> broad_3) and deduplicates by accession.
    """
    max_results = get_expression_atlas_max_results(max_results)
    interpreted = None
    if interpreted_query is not None:
        interpreted = (
            InterpretedQuery.model_validate(interpreted_query)
            if isinstance(interpreted_query, dict)
            else interpreted_query
        )

    search_result = fetch_gxa_repository_records(
        concept_mappings=[],
        max_results=max_results,
        query=query,
        interpreted_query=interpreted,
        species=species,
    )

    results = []
    for record in search_result.get("records", []):
        item = dict(record)
        item["retrieval_strategy"] = item.pop("_retrieval_strategy", None)
        item["retrieval_search_term"] = item.pop("_retrieval_search_term", None)
        results.append(item)

    payload: dict[str, Any] = {
        "query": query,
        "search_term": search_result.get("search_term", query),
        "search_strategies": search_result.get("search_strategies", []),
        "species": species,
        "total_found": search_result.get("total_found", 0),
        "primary_total_found": search_result.get("primary_total_found", 0),
        "results": results,
        "source": "Expression Atlas",
    }
    if search_result.get("message"):
        payload["message"] = search_result["message"]
    if search_result.get("warning"):
        payload["warning"] = search_result["warning"]
    if search_result.get("error"):
        payload["error"] = search_result["error"]
    return payload
