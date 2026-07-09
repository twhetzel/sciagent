"""Vivli / AccessClinicalData@NIAID clinical trial dataset search via the NIAID Discovery API."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchCursor, InterpretedQuery
from domain.evidence_extraction import collect_metadata_fields
from domain.facet_abbreviation_resolution import QUERY_STOPWORDS
from domain.facet_search_strategies import STRATEGY_PRIORITY
from domain.text_broad_search import (
    TEXT_BROAD_STRATEGY,
    finalize_facet_total_found,
    resolve_search_queries_with_text_broad,
    resolve_text_broad_total_found,
    roll_up_facet_totals,
    strategy_count_summary,
)
from domain.repository_vocab import resolve_vivli_facet_value

logger = logging.getLogger(__name__)

NIAID_QUERY_BASE = "https://api.data.niaid.nih.gov/v1/query"
VIVLI_REPOSITORY = "Vivli"
VIVLI_SOURCE = "Vivli / AccessClinicalData@NIAID"
VIVLI_CATALOG_SCOPE = (
    '(includedInDataCatalog.name:"Vivli" OR '
    'includedInDataCatalog.name:"accessclinicaldata@NIAID")'
)
VIVLI_PLATFORM_BASE = "https://vivli.org/members/"
ACCESSCLINICALDATA_BASE = "https://accessclinicaldata.niaid.nih.gov/study-viewer/clinical_trials"
CLINICALTRIALS_BASE = "https://clinicaltrials.gov/study"
DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_CAP = 50
REQUEST_TIMEOUT = 20

VIVLI_ADHOC_STOPWORDS = QUERY_STOPWORDS | frozenset(
    {
        "clinical",
        "trial",
        "trials",
        "dataset",
        "datasets",
        "study",
        "studies",
        "public",
        "controlled",
        "access",
        "vivli",
        "niaid",
    }
)

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")


def get_vivli_max_results(override: int | None = None) -> int:
    """Resolve result limit from explicit arg, env var, or default."""
    if override is not None:
        return max(1, min(int(override), MAX_RESULTS_CAP))

    raw = os.getenv("VIVLI_MAX_RESULTS", str(DEFAULT_MAX_RESULTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_RESULTS
    return max(1, min(value, MAX_RESULTS_CAP))


def _escape_query_term(term: str) -> str:
    return term.replace("\\", "\\\\").replace('"', '\\"')


def _join_names(items: Any) -> str:
    if not items:
        return ""
    if isinstance(items, list):
        names: list[str] = []
        for item in items:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    names.append(name)
            elif item:
                names.append(str(item).strip())
        return ", ".join(names)
    if isinstance(items, dict):
        return str(items.get("name") or "").strip()
    return str(items).strip()


def _compact_adhoc_search_term(query: str) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in WORD_PATTERN.finditer(query):
        token = match.group()
        normalized = token.lower()
        if normalized in VIVLI_ADHOC_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
    return " ".join(tokens[:6])


def _facet_values(
    *,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | dict[str, Any] | None,
) -> dict[str, str | None]:
    if interpreted is not None and isinstance(interpreted, dict):
        interpreted = InterpretedQuery.model_validate(interpreted)
    by_slot = {mapping.slot: mapping.label for mapping in (concept_mappings or [])}
    return {
        "disease": by_slot.get("disease") or (interpreted.disease if interpreted else None),
        "tissue": by_slot.get("tissue") or (interpreted.tissue if interpreted else None),
        "assay": by_slot.get("assay") or (interpreted.assay if interpreted else None),
    }


def _normalize_facet_value(slot: str, value: str | None) -> str | None:
    if not value:
        return None
    return resolve_vivli_facet_value(slot, value) or value.strip()


def _build_vivli_api_query(
    *,
    strategy: str,
    search_term: str,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | dict[str, Any] | None,
) -> str:
    """Build one NIAID Discovery API query for a facet strategy."""
    facets = _facet_values(concept_mappings=concept_mappings, interpreted=interpreted)
    clauses = [VIVLI_CATALOG_SCOPE]

    if strategy == "adhoc":
        compact = _compact_adhoc_search_term(search_term)
        if compact:
            clauses.append(compact)
        return " AND ".join(clauses)

    if strategy == TEXT_BROAD_STRATEGY:
        if search_term.strip():
            clauses.append(search_term.strip())
        return " AND ".join(clauses)

    slot_map = {
        "strict": ("disease", "assay", "tissue"),
        "broad_1": ("disease", "assay"),
        "broad_2": ("disease", "tissue"),
        "broad_3": ("disease",),
    }.get(strategy, ())

    for slot in slot_map:
        value = _normalize_facet_value(slot, facets.get(slot))
        if not value:
            continue
        escaped = _escape_query_term(value)
        if slot == "disease":
            clauses.append(f'healthCondition.name:"{escaped}"')
        elif slot == "tissue":
            clauses.append(
                f'(sample.sampleType.name:"{escaped}" OR "{escaped}")'
            )
        elif slot == "assay":
            clauses.append(f'"{escaped}"')

    if len(clauses) == 1 and search_term.strip():
        clauses.append(search_term.strip())

    return " AND ".join(clauses)


def _niaid_query(
    query: str,
    *,
    size: int,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    response = requests.get(
        NIAID_QUERY_BASE,
        params={"q": query, "size": max(0, size), "from": max(0, offset)},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    hits = data.get("hits") or []
    total = int(data.get("total") or 0)
    return hits, total


def _record_accession(record: dict[str, Any]) -> str:
    nctid = str(record.get("nctid") or "").strip()
    if nctid:
        return nctid.upper()
    identifiers = record.get("identifier") or []
    if isinstance(identifiers, list):
        for item in identifiers:
            value = str(item).strip().upper()
            if value.startswith("NCT"):
                return value
    return ""


def _record_url(record: dict[str, Any], accession: str) -> str:
    url = str(record.get("url") or "").strip()
    if url:
        return url

    catalog = record.get("includedInDataCatalog") or {}
    if isinstance(catalog, dict):
        archived = str(catalog.get("archivedAt") or "").strip()
        if archived:
            return archived
        catalog_name = str(catalog.get("name") or "").strip().lower()
        if "accessclinicaldata" in catalog_name and accession:
            return f"{ACCESSCLINICALDATA_BASE}/{accession}"
        if accession:
            return f"{VIVLI_PLATFORM_BASE}?search={accession}"

    if accession:
        return f"{CLINICALTRIALS_BASE}/{accession}"
    return "https://vivli.org/"


def _record_sample_count(record: dict[str, Any]) -> int | None:
    sample = record.get("sample")
    if not isinstance(sample, dict):
        return None
    quantity = sample.get("sampleQuantity")
    if not isinstance(quantity, dict):
        return None
    value = quantity.get("value")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_species(record: dict[str, Any]) -> str:
    species = record.get("species")
    if isinstance(species, list) and species:
        return _join_names(species)
    if isinstance(species, dict):
        return _join_names(species)
    if species:
        return str(species).strip()
    return "Homo sapiens"


def _parse_vivli_record(record: dict[str, Any]) -> dict[str, Any] | None:
    accession = _record_accession(record)
    if not accession:
        return None

    raw_name = str(record.get("name") or accession).strip()
    title = raw_name
    if title.lower().startswith("dataset from "):
        title = title[len("Dataset from ") :].strip()

    description = str(record.get("description") or record.get("abstract") or "").strip()
    conditions = _join_names(record.get("healthCondition"))
    biosample = ""
    sample = record.get("sample")
    if isinstance(sample, dict):
        sample_type = sample.get("sampleType")
        biosample = _join_names(sample_type)
    assays = _join_names(record.get("measurementTechnique"))
    species = _record_species(record)

    summary_parts = [part for part in (description, conditions, biosample, assays) if part]
    summary = ". ".join(summary_parts)

    catalog = record.get("includedInDataCatalog") or {}
    catalog_name = ""
    if isinstance(catalog, dict):
        catalog_name = str(catalog.get("name") or "").strip()

    return {
        "accession": accession,
        "title": title or accession,
        "description": description,
        "summary": summary,
        "condition_or_disease": conditions,
        "biosample_type": biosample,
        "assay_method": assays,
        "species": species,
        "url": _record_url(record, accession),
        "sample_count": _record_sample_count(record),
        "conditions_of_access": str(record.get("conditionsOfAccess") or "").strip(),
        "data_catalog": catalog_name,
        "doi": str(record.get("doi") or "").strip(),
        "_vivli_source": record,
    }


def _species_matches(species: str | None, record_species: str) -> bool:
    if not species:
        return True
    species_lower = species.lower()
    record_lower = (record_species or "").lower()
    if species_lower in {"human", "homo sapiens"}:
        return "homo sapiens" in record_lower or not record_lower
    return species_lower in record_lower


def _species_from_interpreted(interpreted: InterpretedQuery | None) -> str | None:
    if interpreted and interpreted.organism == "human":
        return "Homo sapiens"
    if interpreted and interpreted.organism:
        return interpreted.organism
    return None


def _resolve_search_queries(
    *,
    query: str,
    interpreted_query: InterpretedQuery | dict[str, Any] | None = None,
    concept_mappings: list[ConceptMapping] | None = None,
    include_text_broad: bool = True,
) -> list[tuple[str, str]]:
    return resolve_search_queries_with_text_broad(
        query=query,
        interpreted_query=interpreted_query,
        concept_mappings=concept_mappings,
        include_text_broad=include_text_broad,
        compact_adhoc_search_term=_compact_adhoc_search_term,
    )


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


def _count_all_vivli_strategies(
    search_queries: list[tuple[str, str]],
    *,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | None,
) -> tuple[list[dict[str, str | int]], int, int, dict[str, int]]:
    strategy_summaries: list[dict[str, str | int]] = []
    strategy_totals: dict[str, int] = {}
    max_facet_total_found = 0
    primary_total_found = 0

    for _, (strategy, search_term) in enumerate(search_queries):
        try:
            api_query = _build_vivli_api_query(
                strategy=strategy,
                search_term=search_term,
                concept_mappings=concept_mappings,
                interpreted=interpreted,
            )
            _, total_found = _niaid_query(api_query, size=0)
            strategy_totals[strategy] = total_found
            max_facet_total_found, primary_total_found = roll_up_facet_totals(
                strategy,
                total_found,
                max_facet_total_found=max_facet_total_found,
                primary_total_found=primary_total_found,
            )
            strategy_summaries.append(
                strategy_count_summary(strategy, search_term, total_found)
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("Vivli count search failed for strategy %s: %s", strategy, exc)
            strategy_totals[strategy] = 0
            strategy_summaries.append(strategy_count_summary(strategy, search_term, 0))

    max_total_found = finalize_facet_total_found(max_facet_total_found, strategy_totals)
    return strategy_summaries, max_total_found, primary_total_found, strategy_totals


def _merge_vivli_record(
    accession_to_record: dict[str, dict[str, Any]],
    accession_priority: dict[str, int],
    parsed: dict[str, Any],
    *,
    strategy: str,
    search_term: str,
) -> bool:
    accession = parsed["accession"]
    priority = STRATEGY_PRIORITY.get(strategy, 99)
    existing_priority = accession_priority.get(accession)
    if existing_priority is not None:
        if priority < existing_priority:
            parsed["_retrieval_strategy"] = strategy
            parsed["_retrieval_search_term"] = search_term
            accession_to_record[accession] = parsed
            accession_priority[accession] = priority
        return False

    parsed["_retrieval_strategy"] = strategy
    parsed["_retrieval_search_term"] = search_term
    accession_to_record[accession] = parsed
    accession_priority[accession] = priority
    return True


def _collect_vivli_record_batch(
    search_queries: list[tuple[str, str]],
    *,
    batch_size: int,
    per_strategy_page: int,
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
    seen_accessions: set[str],
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | None,
    species: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, str | int]]]:
    accession_to_record: dict[str, dict[str, Any]] = {}
    accession_priority: dict[str, int] = {}
    updated_offsets = dict(strategy_offsets)
    batch_stats: list[dict[str, str | int]] = []

    for strategy, search_term in search_queries:
        retrieved = 0
        new_ids = 0
        offset = updated_offsets.get(strategy, 0)
        total_for_strategy = strategy_totals.get(strategy, 0)
        api_query = _build_vivli_api_query(
            strategy=strategy,
            search_term=search_term,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
        )

        while len(accession_to_record) < batch_size and offset < total_for_strategy:
            remaining_batch = batch_size - len(accession_to_record)
            remaining_strategy = total_for_strategy - offset
            page_size = min(per_strategy_page, remaining_batch, remaining_strategy)
            if page_size <= 0:
                break

            entries, hit_count = _niaid_query(api_query, size=page_size, offset=offset)
            strategy_totals[strategy] = hit_count
            total_for_strategy = hit_count
            retrieved += len(entries)

            if not entries:
                offset = total_for_strategy
                break

            for entry in entries:
                parsed = _parse_vivli_record(entry)
                if not parsed:
                    continue
                if not _species_matches(species, parsed.get("species", "")):
                    continue
                if parsed["accession"] in seen_accessions:
                    continue
                if _merge_vivli_record(
                    accession_to_record,
                    accession_priority,
                    parsed,
                    strategy=strategy,
                    search_term=search_term,
                ):
                    new_ids += 1
                if len(accession_to_record) >= batch_size:
                    break

            offset += len(entries)

        updated_offsets[strategy] = offset
        batch_stats.append(
            {
                "strategy": strategy,
                "search_term": search_term,
                "retrieved": retrieved,
                "new_ids": new_ids,
            }
        )

        if len(accession_to_record) >= batch_size:
            break

    records = sorted(
        accession_to_record.values(),
        key=lambda item: (
            STRATEGY_PRIORITY.get(item.get("_retrieval_strategy"), 99),
            item.get("accession", ""),
        ),
    )
    return records, updated_offsets, batch_stats


def _build_vivli_cursor(
    *,
    concept_mappings: list[ConceptMapping],
    search_queries: list[tuple[str, str]],
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
    seen_accessions: set[str],
    max_results: int,
    total_found: int,
    primary_total_found: int,
    primary_search_term: str,
    query: str = "",
    interpreted_query: InterpretedQuery | dict[str, Any] | None = None,
    include_text_broad: bool = True,
) -> DatasetSearchCursor:
    interpreted = (
        InterpretedQuery.model_validate(interpreted_query)
        if isinstance(interpreted_query, dict)
        else (interpreted_query or InterpretedQuery())
    )
    return DatasetSearchCursor(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        strategy_offsets=strategy_offsets,
        strategy_totals=strategy_totals,
        seen_accessions=sorted(seen_accessions),
        total_found=total_found,
        primary_total_found=primary_total_found,
        text_broad_total_found=resolve_text_broad_total_found(
            strategy_totals,
            include_text_broad=include_text_broad,
        ),
        max_results=max_results,
        search_term=primary_search_term,
        repository=VIVLI_REPOSITORY,
        include_text_broad=include_text_broad,
        has_more=_compute_has_more(search_queries, strategy_offsets, strategy_totals),
    )


def _build_source_metadata(record: dict[str, Any]) -> dict[str, str]:
    keys = (
        "conditions_of_access",
        "data_catalog",
        "doi",
        "condition_or_disease",
        "biosample_type",
        "assay_method",
        "species",
    )
    metadata = {
        key: str(record.get(key)).strip()
        for key in keys
        if str(record.get(key) or "").strip()
    }
    metadata["source"] = VIVLI_SOURCE
    metadata["access_profile"] = "controlled_or_request_based"
    return metadata


def normalize_vivli_record(
    record: dict[str, Any],
    *,
    retrieval_strategy: str | None = None,
    retrieval_search_term: str | None = None,
) -> DatasetCandidate | None:
    """Convert one Vivli / NIAID Discovery record into a shared DatasetCandidate."""
    accession = str(record.get("accession") or "").strip()
    if not accession:
        return None

    title = str(record.get("title") or "Untitled study").strip()
    description = str(record.get("description") or "").strip()
    summary = str(record.get("summary") or description).strip()
    assay_method = str(record.get("assay_method") or "").strip()
    metadata_fields = collect_metadata_fields(
        title=title,
        description=summary,
        taxon=record.get("species"),
        gdstype=assay_method or None,
    )
    if record.get("condition_or_disease"):
        metadata_fields["condition_or_disease"] = str(record["condition_or_disease"])
    if record.get("biosample_type"):
        metadata_fields["biosample_type"] = str(record["biosample_type"])
    if assay_method:
        metadata_fields["assay_method"] = assay_method

    return DatasetCandidate(
        repository=VIVLI_REPOSITORY,
        accession=accession,
        title=title,
        description=description,
        sample_count=record.get("sample_count"),
        url=str(record.get("url") or _record_url(record, accession)),
        metadata_fields=metadata_fields,
        observed_disease=str(record.get("condition_or_disease") or "").strip() or None,
        observed_tissue=str(record.get("biosample_type") or "").strip() or None,
        observed_assay=assay_method or None,
        observed_organism=str(record.get("species") or "").strip() or None,
        source_metadata=_build_source_metadata(record),
        retrieval_strategy=retrieval_strategy or record.get("_retrieval_strategy"),
        retrieval_search_term=retrieval_search_term or record.get("_retrieval_search_term"),
    )


def normalize_vivli_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_vivli_record(record)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_vivli_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    include_text_broad: bool = True,
) -> dict[str, Any]:
    """Search Vivli / AccessClinicalData@NIAID metadata with multi-strategy facet queries."""
    max_results = get_vivli_max_results(max_results)
    interpreted = None
    if interpreted_query is not None:
        interpreted = (
            InterpretedQuery.model_validate(interpreted_query)
            if isinstance(interpreted_query, dict)
            else interpreted_query
        )
    search_queries = _resolve_search_queries(
        query=query,
        interpreted_query=interpreted,
        concept_mappings=concept_mappings,
        include_text_broad=include_text_broad,
    )

    if not search_queries:
        return {
            "search_term": "",
            "search_strategies": [],
            "total_found": 0,
            "primary_total_found": 0,
            "text_broad_total_found": None,
            "include_text_broad": include_text_broad,
            "max_results": max_results,
            "records": [],
            "source": VIVLI_SOURCE,
            "repository": VIVLI_REPOSITORY,
            "has_more": False,
            "load_more_cursor": None,
            "error": "No grounded concepts available for Vivli search",
        }

    per_strategy_page = max(5, max_results)
    primary_search_term = search_queries[0][1]
    species = _species_from_interpreted(interpreted)
    errors: list[str] = []

    strategy_summaries, max_total_found, primary_total_found, strategy_totals = (
        _count_all_vivli_strategies(
            search_queries,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
        )
    )

    seen_accessions: set[str] = set()
    strategy_offsets = {strategy: 0 for strategy, _ in search_queries}

    try:
        records, strategy_offsets, batch_stats = _collect_vivli_record_batch(
            search_queries,
            batch_size=max_results,
            per_strategy_page=per_strategy_page,
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_accessions=seen_accessions,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
            species=species,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("Vivli search batch failed: %s", exc)
        errors.append(f"search batch: {exc}")
        records = []
        batch_stats = []

    for summary in strategy_summaries:
        for batch in batch_stats:
            if summary["strategy"] == batch["strategy"]:
                summary["retrieved"] = batch["retrieved"]
                summary["new_ids"] = batch["new_ids"]
                break

    for record in records:
        seen_accessions.add(record["accession"])

    cursor = _build_vivli_cursor(
        concept_mappings=concept_mappings,
        search_queries=search_queries,
        strategy_offsets=strategy_offsets,
        strategy_totals=strategy_totals,
        seen_accessions=seen_accessions,
        max_results=max_results,
        total_found=max_total_found,
        primary_total_found=primary_total_found,
        primary_search_term=primary_search_term,
        query=query,
        interpreted_query=interpreted,
        include_text_broad=include_text_broad,
    )

    text_broad_total_found = resolve_text_broad_total_found(
        strategy_totals,
        include_text_broad=include_text_broad,
    )

    payload: dict[str, Any] = {
        "search_term": primary_search_term,
        "search_strategies": strategy_summaries,
        "total_found": max_total_found,
        "primary_total_found": primary_total_found,
        "text_broad_total_found": text_broad_total_found,
        "include_text_broad": include_text_broad,
        "max_results": max_results,
        "records": records,
        "source": VIVLI_SOURCE,
        "repository": VIVLI_REPOSITORY,
        "has_more": cursor.has_more,
        "load_more_cursor": cursor.model_dump() if cursor.has_more else None,
    }
    if errors:
        payload["error"] = "; ".join(errors)
    return payload


def fetch_more_vivli_repository_records(cursor: DatasetSearchCursor) -> dict[str, Any]:
    """Load the next batch of Vivli studies from cursor offsets."""
    search_queries = _resolve_search_queries(
        query=cursor.query,
        interpreted_query=cursor.interpreted_query,
        concept_mappings=cursor.concept_mappings,
        include_text_broad=cursor.include_text_broad,
    )
    if not search_queries:
        return {
            "records": [],
            "added_count": 0,
            "has_more": False,
            "load_more_cursor": None,
            "source": VIVLI_SOURCE,
            "repository": VIVLI_REPOSITORY,
            "error": "Cursor has no search strategies",
        }

    seen_accessions = set(cursor.seen_accessions)
    strategy_offsets = dict(cursor.strategy_offsets)
    strategy_totals = dict(cursor.strategy_totals)
    species = _species_from_interpreted(cursor.interpreted_query)

    try:
        records, strategy_offsets, _batch_stats = _collect_vivli_record_batch(
            search_queries,
            batch_size=cursor.max_results,
            per_strategy_page=max(5, cursor.max_results),
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_accessions=seen_accessions,
            concept_mappings=cursor.concept_mappings,
            interpreted=cursor.interpreted_query,
            species=species,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("Vivli load-more batch failed: %s", exc)
        return {
            "records": [],
            "added_count": 0,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "source": VIVLI_SOURCE,
            "repository": VIVLI_REPOSITORY,
            "error": str(exc),
        }

    for record in records:
        seen_accessions.add(record["accession"])

    updated_cursor = _build_vivli_cursor(
        concept_mappings=cursor.concept_mappings,
        search_queries=search_queries,
        strategy_offsets=strategy_offsets,
        strategy_totals=strategy_totals,
        seen_accessions=seen_accessions,
        max_results=cursor.max_results,
        total_found=cursor.total_found,
        primary_total_found=cursor.primary_total_found or 0,
        primary_search_term=cursor.search_term or search_queries[0][1],
        query=cursor.query,
        interpreted_query=cursor.interpreted_query,
        include_text_broad=cursor.include_text_broad,
    )

    return {
        "records": records,
        "added_count": len(records),
        "has_more": updated_cursor.has_more,
        "load_more_cursor": updated_cursor.model_dump() if updated_cursor.has_more else None,
        "include_text_broad": cursor.include_text_broad,
        "text_broad_total_found": updated_cursor.text_broad_total_found,
        "source": VIVLI_SOURCE,
        "repository": VIVLI_REPOSITORY,
    }


def search_vivli_datasets(
    query: str,
    *,
    max_results: int | None = None,
    interpreted_query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Agent-facing Vivli search wrapper."""
    payload = fetch_vivli_repository_records(
        [],
        max_results=max_results,
        query=query,
        interpreted_query=interpreted_query,
    )
    candidates = normalize_vivli_records(payload.get("records") or [])
    return {
        "results": [candidate.model_dump() for candidate in candidates],
        "total_found": payload.get("total_found", 0),
        "primary_total_found": payload.get("primary_total_found"),
        "search_term": payload.get("search_term"),
        "search_strategies": payload.get("search_strategies", []),
        "source": VIVLI_SOURCE,
        "repository": VIVLI_REPOSITORY,
        "has_more": payload.get("has_more", False),
        "load_more_cursor": payload.get("load_more_cursor"),
        "error": payload.get("error"),
    }
