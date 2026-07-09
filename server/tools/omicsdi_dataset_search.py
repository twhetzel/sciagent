"""OmicsDI multi-omics dataset search via the OmicsDI REST API."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchCursor, InterpretedQuery
from domain.evidence_extraction import collect_metadata_fields
from domain.omicsdi_assay import annotate_omicsdi_metadata_fields, infer_observed_assay_from_omicsdi_metadata
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
from domain.repository_vocab.omicsdi_vocab import (
    omicsdi_assay_filter_clauses,
    resolve_omicsdi_facet_value,
)

logger = logging.getLogger(__name__)

OMICSDI_SEARCH_BASE = "https://www.omicsdi.org/ws/dataset/search"
OMICSDI_DATASET_BASE = "https://www.omicsdi.org/ws/dataset"
OMICSDI_PLATFORM_BASE = "https://www.omicsdi.org/dataset"
OMICSDI_REPOSITORY = "OmicsDI"
OMICSDI_SOURCE = "OmicsDI API"
DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_CAP = 50
REQUEST_TIMEOUT = 20
MAX_PAGE_SIZE = 100

OMICSDI_ADHOC_STOPWORDS = QUERY_STOPWORDS | frozenset(
    {
        "dataset",
        "datasets",
        "public",
        "omics",
        "omicsdi",
        "find",
        "multi",
    }
)

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")

QUERY_OMICS_TYPE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brna[\s-]?seq(?:uencing)?\b", re.I), "Transcriptomics"),
    (re.compile(r"\btranscriptome\b", re.I), "Transcriptomics"),
    (re.compile(r"\bproteomics\b", re.I), "Proteomics"),
    (re.compile(r"\bmetabolomics\b", re.I), "Metabolomics"),
    (re.compile(r"\bgenomics\b", re.I), "Genomics"),
)


def _infer_assay_from_query(query: str) -> str | None:
    for pattern, omics_type in QUERY_OMICS_TYPE_PATTERNS:
        if pattern.search(query):
            return omics_type
    return None


def get_omicsdi_max_results(override: int | None = None) -> int:
    """Resolve result limit from explicit arg, env var, or default."""
    if override is not None:
        return max(1, min(int(override), MAX_RESULTS_CAP))

    raw = os.getenv("OMICSDI_MAX_RESULTS", str(DEFAULT_MAX_RESULTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_RESULTS
    return max(1, min(value, MAX_RESULTS_CAP))


def _escape_query_term(term: str) -> str:
    return term.replace("\\", "\\\\").replace('"', '\\"')


def _join_list(values: Any) -> str:
    if not values:
        return ""
    if isinstance(values, list):
        parts = [str(item).strip() for item in values if str(item).strip()]
        return ", ".join(parts)
    return str(values).strip()


def _compact_adhoc_search_term(query: str) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in WORD_PATTERN.finditer(query):
        token = match.group()
        normalized = token.lower()
        if normalized in OMICSDI_ADHOC_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
    return " ".join(tokens[:6])


def _facet_values(
    *,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | dict[str, Any] | None,
    query: str = "",
) -> dict[str, str | None]:
    if interpreted is not None and isinstance(interpreted, dict):
        interpreted = InterpretedQuery.model_validate(interpreted)
    by_slot = {mapping.slot: mapping.label for mapping in (concept_mappings or [])}
    assay = by_slot.get("assay") or (interpreted.assay if interpreted else None)
    if not assay and query.strip():
        assay = _infer_assay_from_query(query)
    return {
        "disease": by_slot.get("disease") or (interpreted.disease if interpreted else None),
        "tissue": by_slot.get("tissue") or (interpreted.tissue if interpreted else None),
        "assay": assay,
        "organism": by_slot.get("organism") or (interpreted.organism if interpreted else None),
    }


def _normalize_facet_value(slot: str, value: str | None) -> str | None:
    if not value:
        return None
    return resolve_omicsdi_facet_value(slot, value) or value.strip()


def _organism_clause(organism: str | None) -> str | None:
    if not organism:
        return None
    taxon = resolve_omicsdi_facet_value("organism", organism)
    if taxon and taxon.isdigit():
        return f'TAXONOMY:"{taxon}"'
    return None


def _build_omicsdi_api_query(
    *,
    strategy: str,
    search_term: str,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | dict[str, Any] | None,
    query: str = "",
) -> str:
    """Build one OmicsDI search query for a facet strategy."""
    facets = _facet_values(
        concept_mappings=concept_mappings,
        interpreted=interpreted,
        query=query,
    )
    organism_clause = _organism_clause(facets.get("organism"))

    if strategy == "adhoc":
        compact = _compact_adhoc_search_term(search_term)
        clauses = [compact or search_term.strip()]
        if organism_clause:
            clauses.append(organism_clause)
        return " AND ".join(clause for clause in clauses if clause)

    if strategy == TEXT_BROAD_STRATEGY:
        clauses = [search_term.strip()]
        if organism_clause:
            clauses.append(organism_clause)
        return " AND ".join(clause for clause in clauses if clause)

    slot_map = {
        "strict": ("disease", "assay", "tissue"),
        "broad_1": ("disease", "assay"),
        "broad_2": ("disease", "tissue"),
        "broad_3": ("disease",),
    }.get(strategy, ())

    clauses: list[str] = []
    for slot in slot_map:
        value = _normalize_facet_value(slot, facets.get(slot))
        if not value:
            continue
        escaped = _escape_query_term(value)
        if slot == "disease":
            clauses.append(f'disease:"{escaped}"')
        elif slot == "tissue":
            clauses.append(f'tissue:"{escaped}"')
        elif slot == "assay":
            clauses.extend(omicsdi_assay_filter_clauses(value))

    if organism_clause:
        clauses.append(organism_clause)

    if not clauses and search_term.strip():
        clauses.append(search_term.strip())

    return " AND ".join(clauses)


def _omicsdi_search(
    query: str,
    *,
    size: int,
    start: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    response = requests.get(
        OMICSDI_SEARCH_BASE,
        params={"query": query, "size": max(0, min(size, MAX_PAGE_SIZE)), "start": max(0, start)},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    datasets = data.get("datasets") or []
    total = int(data.get("count") or 0)
    return datasets, total


def _dataset_platform_url(source: str, dataset_id: str) -> str:
    source_slug = (source or "").strip().lower()
    return f"{OMICSDI_PLATFORM_BASE}/{source_slug}/{dataset_id}"


def _join_organisms(organisms: Any) -> str:
    if not isinstance(organisms, list):
        return ""
    names: list[str] = []
    for item in organisms:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        elif item:
            names.append(str(item).strip())
    return ", ".join(names)


def _join_keywords(keywords: Any) -> str:
    if not keywords:
        return ""
    if isinstance(keywords, list):
        return ", ".join(str(item).strip() for item in keywords if str(item).strip())
    return str(keywords).strip()


def _fetch_dataset_detail(source: str, dataset_id: str) -> dict[str, Any] | None:
    source_slug = (source or "").strip().lower()
    if not source_slug or not dataset_id:
        return None
    try:
        response = requests.get(
            f"{OMICSDI_DATASET_BASE}/{source_slug}/{dataset_id}",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except requests.RequestException as exc:
        logger.warning("OmicsDI detail fetch failed for %s/%s: %s", source_slug, dataset_id, exc)
    return None


def _detail_structured_fields(detail: dict[str, Any] | None) -> dict[str, str]:
    if not detail:
        return {}
    additional = detail.get("additional") or {}
    if not isinstance(additional, dict):
        return {}

    fields: dict[str, str] = {}
    disease = _join_list(additional.get("disease"))
    tissue = _join_list(additional.get("tissue"))
    technology = _join_list(additional.get("technology_type"))
    if disease:
        fields["condition_or_disease"] = disease
    if tissue:
        fields["biosample_type"] = tissue
    if technology:
        fields["assay_method"] = technology
    return fields


def _parse_omicsdi_record(entry: dict[str, Any], *, enrich: bool = True) -> dict[str, Any] | None:
    dataset_id = str(entry.get("id") or "").strip()
    source = str(entry.get("source") or "").strip()
    if not dataset_id:
        return None

    title = str(entry.get("title") or dataset_id).strip()
    description = str(entry.get("description") or "").strip()
    keywords = _join_keywords(entry.get("keywords"))
    omics_type = _join_list(entry.get("omicsType"))
    species = _join_organisms(entry.get("organisms"))

    structured: dict[str, str] = {}
    if enrich:
        structured = _detail_structured_fields(_fetch_dataset_detail(source, dataset_id))

    if not structured.get("assay_method") and omics_type:
        structured["assay_method"] = omics_type

    summary_parts = [part for part in (description, keywords, omics_type, species) if part]
    summary = ". ".join(summary_parts)

    return {
        "accession": dataset_id,
        "title": title,
        "description": description,
        "summary": summary,
        "condition_or_disease": structured.get("condition_or_disease", ""),
        "biosample_type": structured.get("biosample_type", ""),
        "assay_method": structured.get("assay_method", omics_type),
        "species": species,
        "url": _dataset_platform_url(source, dataset_id),
        "omics_type": omics_type,
        "keywords": keywords,
        "source_database": source,
        "publication_date": str(entry.get("publicationDate") or "").strip(),
        "_source_repository": OMICSDI_REPOSITORY,
        "_omicsdi_source": entry,
    }


def _species_matches(species: str | None, record_species: str) -> bool:
    if not species:
        return True
    species_lower = species.lower()
    record_lower = (record_species or "").lower()
    if species_lower in {"human", "homo sapiens", "9606"}:
        return "homo sapiens" in record_lower or "9606" in record_lower
    if species_lower in {"mouse", "mus musculus", "10090"}:
        return "mus musculus" in record_lower or "10090" in record_lower
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


def _count_all_omicsdi_strategies(
    search_queries: list[tuple[str, str]],
    *,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | None,
    query: str = "",
) -> tuple[list[dict[str, str | int]], int, int, dict[str, int]]:
    strategy_summaries: list[dict[str, str | int]] = []
    strategy_totals: dict[str, int] = {}
    max_facet_total_found = 0
    primary_total_found = 0

    for _, (strategy, search_term) in enumerate(search_queries):
        try:
            api_query = _build_omicsdi_api_query(
                strategy=strategy,
                search_term=search_term,
                concept_mappings=concept_mappings,
                interpreted=interpreted,
                query=query,
            )
            _, total_found = _omicsdi_search(api_query, size=0)
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
            logger.warning("OmicsDI count search failed for strategy %s: %s", strategy, exc)
            strategy_totals[strategy] = 0
            strategy_summaries.append(strategy_count_summary(strategy, search_term, 0))

    max_total_found = finalize_facet_total_found(max_facet_total_found, strategy_totals)
    return strategy_summaries, max_total_found, primary_total_found, strategy_totals


def _merge_omicsdi_record(
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


def _collect_omicsdi_record_batch(
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
    enrich: bool = True,
    query: str = "",
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
        api_query = _build_omicsdi_api_query(
            strategy=strategy,
            search_term=search_term,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
            query=query,
        )

        while len(accession_to_record) < batch_size and offset < total_for_strategy:
            remaining_batch = batch_size - len(accession_to_record)
            remaining_strategy = total_for_strategy - offset
            page_size = min(per_strategy_page, remaining_batch, remaining_strategy, MAX_PAGE_SIZE)
            if page_size <= 0:
                break

            entries, hit_count = _omicsdi_search(api_query, size=page_size, start=offset)
            strategy_totals[strategy] = hit_count
            total_for_strategy = hit_count
            retrieved += len(entries)

            if not entries:
                offset = total_for_strategy
                break

            for entry in entries:
                parsed = _parse_omicsdi_record(entry, enrich=enrich)
                if not parsed:
                    continue
                if not _species_matches(species, parsed.get("species", "")):
                    continue
                if parsed["accession"] in seen_accessions:
                    continue
                if _merge_omicsdi_record(
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


def _build_omicsdi_cursor(
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
        repository=OMICSDI_REPOSITORY,
        include_text_broad=include_text_broad,
        has_more=_compute_has_more(search_queries, strategy_offsets, strategy_totals),
    )


def _build_source_metadata(record: dict[str, Any]) -> dict[str, str]:
    keys = (
        "condition_or_disease",
        "biosample_type",
        "assay_method",
        "species",
        "omics_type",
        "keywords",
        "source_database",
        "publication_date",
    )
    metadata = {
        key: str(record.get(key)).strip()
        for key in keys
        if str(record.get(key) or "").strip()
    }
    metadata["source"] = OMICSDI_SOURCE
    metadata["access_profile"] = "mixed"
    return metadata


def normalize_omicsdi_record(
    record: dict[str, Any],
    *,
    retrieval_strategy: str | None = None,
    retrieval_search_term: str | None = None,
) -> DatasetCandidate | None:
    """Convert one OmicsDI record into a shared DatasetCandidate."""
    accession = str(record.get("accession") or "").strip()
    if not accession:
        return None

    title = str(record.get("title") or "Untitled dataset").strip()
    description = str(record.get("description") or "").strip()
    summary = str(record.get("summary") or description).strip()
    assay_method = str(record.get("assay_method") or "").strip()
    omics_type = str(record.get("omics_type") or "").strip()
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
    metadata_fields = annotate_omicsdi_metadata_fields(
        metadata_fields,
        omics_type=omics_type,
        assay_method=assay_method,
    )
    observed_assay = metadata_fields.get("omicsdi_observed_assay") or infer_observed_assay_from_omicsdi_metadata(
        omics_type=omics_type,
        assay_method=assay_method,
    )
    if observed_assay == "unknown":
        observed_assay = assay_method or omics_type or None

    return DatasetCandidate(
        repository=OMICSDI_REPOSITORY,
        accession=accession,
        title=title,
        description=description,
        url=str(record.get("url") or _dataset_platform_url(record.get("source_database", ""), accession)),
        metadata_fields=metadata_fields,
        observed_disease=str(record.get("condition_or_disease") or "").strip() or None,
        observed_tissue=str(record.get("biosample_type") or "").strip() or None,
        observed_assay=observed_assay if observed_assay else None,
        observed_organism=str(record.get("species") or "").strip() or None,
        source_metadata=_build_source_metadata(record),
        retrieval_strategy=retrieval_strategy or record.get("_retrieval_strategy"),
        retrieval_search_term=retrieval_search_term or record.get("_retrieval_search_term"),
    )


def normalize_omicsdi_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_omicsdi_record(record)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_omicsdi_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    include_text_broad: bool = True,
) -> dict[str, Any]:
    """Search OmicsDI with multi-strategy facet queries."""
    max_results = get_omicsdi_max_results(max_results)
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
            "source": OMICSDI_SOURCE,
            "repository": OMICSDI_REPOSITORY,
            "has_more": False,
            "load_more_cursor": None,
            "error": "No grounded concepts available for OmicsDI search",
        }

    per_strategy_page = max(5, max_results)
    primary_search_term = search_queries[0][1]
    species = _species_from_interpreted(interpreted)
    errors: list[str] = []

    strategy_summaries, max_total_found, primary_total_found, strategy_totals = (
        _count_all_omicsdi_strategies(
            search_queries,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
            query=query,
        )
    )

    seen_accessions: set[str] = set()
    strategy_offsets = {strategy: 0 for strategy, _ in search_queries}

    try:
        records, strategy_offsets, batch_stats = _collect_omicsdi_record_batch(
            search_queries,
            batch_size=max_results,
            per_strategy_page=per_strategy_page,
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_accessions=seen_accessions,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
            species=species,
            query=query,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("OmicsDI search batch failed: %s", exc)
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

    cursor = _build_omicsdi_cursor(
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
        "source": OMICSDI_SOURCE,
        "repository": OMICSDI_REPOSITORY,
        "has_more": cursor.has_more,
        "load_more_cursor": cursor.model_dump() if cursor.has_more else None,
    }
    if errors:
        payload["error"] = "; ".join(errors)
    return payload


def fetch_more_omicsdi_repository_records(cursor: DatasetSearchCursor) -> dict[str, Any]:
    """Load the next batch of OmicsDI datasets from cursor offsets."""
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
            "source": OMICSDI_SOURCE,
            "repository": OMICSDI_REPOSITORY,
            "error": "Cursor has no search strategies",
        }

    seen_accessions = set(cursor.seen_accessions)
    strategy_offsets = dict(cursor.strategy_offsets)
    strategy_totals = dict(cursor.strategy_totals)
    species = _species_from_interpreted(cursor.interpreted_query)

    try:
        records, strategy_offsets, _batch_stats = _collect_omicsdi_record_batch(
            search_queries,
            batch_size=cursor.max_results,
            per_strategy_page=max(5, cursor.max_results),
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_accessions=seen_accessions,
            concept_mappings=cursor.concept_mappings,
            interpreted=cursor.interpreted_query,
            species=species,
            query=cursor.query,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("OmicsDI load-more batch failed: %s", exc)
        return {
            "records": [],
            "added_count": 0,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "source": OMICSDI_SOURCE,
            "repository": OMICSDI_REPOSITORY,
            "error": str(exc),
        }

    for record in records:
        seen_accessions.add(record["accession"])

    updated_cursor = _build_omicsdi_cursor(
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
        "source": OMICSDI_SOURCE,
        "repository": OMICSDI_REPOSITORY,
    }


def search_omicsdi_datasets(
    query: str,
    *,
    max_results: int | None = None,
    interpreted_query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Agent-facing OmicsDI search wrapper."""
    payload = fetch_omicsdi_repository_records(
        [],
        max_results=max_results,
        query=query,
        interpreted_query=interpreted_query,
    )
    candidates = normalize_omicsdi_records(payload.get("records") or [])
    return {
        "results": [candidate.model_dump() for candidate in candidates],
        "total_found": payload.get("total_found", 0),
        "primary_total_found": payload.get("primary_total_found"),
        "search_term": payload.get("search_term"),
        "search_strategies": payload.get("search_strategies", []),
        "source": OMICSDI_SOURCE,
        "repository": OMICSDI_REPOSITORY,
        "has_more": payload.get("has_more", False),
        "load_more_cursor": payload.get("load_more_cursor"),
        "error": payload.get("error"),
    }
