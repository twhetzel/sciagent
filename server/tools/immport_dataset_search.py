"""ImmPort shared-data study search via the ImmPort Shared Data API."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchCursor, InterpretedQuery
from domain.evidence_extraction import collect_metadata_fields
from domain.facet_abbreviation_resolution import QUERY_STOPWORDS
from domain.facet_search_strategies import STRATEGY_PRIORITY, build_facet_search_queries
from domain.repository_vocab import resolve_immport_facet_value

logger = logging.getLogger(__name__)

IMMPORT_SEARCH_BASE = "https://www.immport.org/data/query/api/search/study"
IMMPORT_STUDY_BASE = "https://www.immport.org/shared/study"
IMMPORT_REPOSITORY = "ImmPort"
IMMPORT_FACET_STRATEGIES = frozenset({"strict", "broad_1", "broad_2", "broad_3"})
TEXT_BROAD_STRATEGY = "text_broad"
DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_CAP = 50
REQUEST_TIMEOUT = 15

IMMPORT_SOURCE_FIELDS = (
    "study_accession,brief_title,brief_description,condition_or_disease,"
    "biosample_type,assay_method,species,research_focus,program_name,"
    "clinical_trial,actual_enrollment,doi,pubmed_id,has_assessment,"
    "has_lab_test,latest_data_release_version,latest_data_release_date,"
    "study_pi,gender_included"
)

# Legacy static overrides; repository_vocab resolves against ImmPort lookup tables first.
IMMPORT_FACET_VALUES: dict[tuple[str, str], str] = {
    ("assay", "flow cytometry"): "Flow Cytometry",
    ("tissue", "pbmc"): "PBMC",
    ("tissue", "pbmcs"): "PBMC",
}

IMMPORT_ADHOC_STOPWORDS = QUERY_STOPWORDS | frozenset(
    {
        "immunology",
        "immunological",
        "study",
        "studies",
        "omics",
    }
)

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")


def _normalize_facet_value(slot: str, value: str | None) -> str | None:
    if not value:
        return None
    resolved = resolve_immport_facet_value(slot, value)
    if resolved:
        return resolved
    mapped = IMMPORT_FACET_VALUES.get((slot, value.strip().lower()))
    return mapped or value.strip()


def _compact_adhoc_search_term(query: str) -> str:
    """Drop dataset-discovery boilerplate before ImmPort free-text search."""
    tokens: list[str] = []
    seen: set[str] = set()
    for match in WORD_PATTERN.finditer(query):
        token = match.group()
        normalized = token.lower()
        if normalized in IMMPORT_ADHOC_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
    return " ".join(tokens[:6])


def get_immport_max_results(override: int | None = None) -> int:
    """Resolve result limit from explicit arg, env var, or default."""
    if override is not None:
        return max(1, min(int(override), MAX_RESULTS_CAP))

    raw = os.getenv("IMMPORT_MAX_RESULTS", str(DEFAULT_MAX_RESULTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_RESULTS
    return max(1, min(value, MAX_RESULTS_CAP))


def _join_values(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _study_url(accession: str) -> str:
    return f"{IMMPORT_STUDY_BASE}/{accession}"


def _species_matches(species: str | None, record_species: str) -> bool:
    if not species:
        return True
    species_lower = species.lower()
    record_lower = record_species.lower()
    if species_lower in {"human", "homo sapiens"}:
        return "homo sapiens" in record_lower
    return species_lower in record_lower


def _species_from_interpreted(interpreted: InterpretedQuery | None) -> str | None:
    if interpreted and interpreted.organism == "human":
        return "Homo sapiens"
    if interpreted and interpreted.organism:
        return interpreted.organism
    return None


def _build_immport_search_params(
    *,
    search_term: str,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | None,
    strategy: str,
    page_size: int,
    from_record: int | None = None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "pageSize": page_size,
        "sourceFields": IMMPORT_SOURCE_FIELDS,
    }
    if from_record is not None:
        params["fromRecord"] = from_record

    by_slot = {mapping.slot: mapping.label for mapping in (concept_mappings or [])}
    disease = by_slot.get("disease") or (interpreted.disease if interpreted else None)
    assay = by_slot.get("assay") or (interpreted.assay if interpreted else None)
    tissue = by_slot.get("tissue") or (interpreted.tissue if interpreted else None)
    species = _species_from_interpreted(interpreted)

    if strategy == "strict":
        if disease:
            params["conditionOrDisease"] = _normalize_facet_value("disease", disease)
        if assay:
            params["assayMethod"] = _normalize_facet_value("assay", assay)
        if tissue:
            params["biosampleType"] = _normalize_facet_value("tissue", tissue)
    elif strategy == "broad_1":
        if disease:
            params["conditionOrDisease"] = _normalize_facet_value("disease", disease)
        if assay:
            params["assayMethod"] = _normalize_facet_value("assay", assay)
    elif strategy == "broad_2":
        if disease:
            params["conditionOrDisease"] = _normalize_facet_value("disease", disease)
        if tissue:
            params["biosampleType"] = _normalize_facet_value("tissue", tissue)
    elif strategy in {"broad_3", "adhoc"}:
        if disease:
            params["conditionOrDisease"] = _normalize_facet_value("disease", disease)
    elif strategy == TEXT_BROAD_STRATEGY:
        pass

    if species:
        params["species"] = species

    # Facet strategies: CV filters only (NDE/CDT parity). text_broad/adhoc: free-text `term` only.
    has_facet_filter = any(
        params.get(key)
        for key in ("conditionOrDisease", "assayMethod", "biosampleType")
    )
    if search_term.strip() and (strategy in {TEXT_BROAD_STRATEGY, "adhoc"} or not has_facet_filter):
        params["term"] = search_term.strip()

    return params


def _immport_study_search(params: dict[str, str | int]) -> tuple[list[dict[str, Any]], int]:
    response = requests.get(
        IMMPORT_SEARCH_BASE,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    hits = data.get("hits") or {}
    total = hits.get("total") or {}
    total_found = int(total.get("value", 0)) if isinstance(total, dict) else int(total or 0)
    records = [
        hit.get("_source")
        for hit in hits.get("hits", [])
        if isinstance(hit.get("_source"), dict)
    ]
    return records, total_found


def _parse_immport_record(source: dict[str, Any]) -> dict[str, Any] | None:
    accession = str(source.get("study_accession") or "").strip()
    if not accession:
        return None

    title = str(source.get("brief_title") or accession).strip()
    description = str(source.get("brief_description") or "").strip()
    conditions = _join_values(source.get("condition_or_disease"))
    biosamples = _join_values(source.get("biosample_type"))
    assays = _join_values(source.get("assay_method"))
    species = _join_values(source.get("species"))

    summary_parts = [part for part in (description, conditions, biosamples, assays) if part]
    summary = ". ".join(summary_parts)

    enrollment = source.get("actual_enrollment")
    sample_count = None
    if enrollment not in (None, ""):
        try:
            sample_count = int(enrollment)
        except (TypeError, ValueError):
            sample_count = None

    return {
        "accession": accession,
        "title": title,
        "description": description,
        "summary": summary,
        "condition_or_disease": conditions,
        "biosample_type": biosamples,
        "assay_method": assays,
        "species": species,
        "research_focus": _join_values(source.get("research_focus")),
        "program_name": _join_values(source.get("program_name")),
        "clinical_trial": str(source.get("clinical_trial") or "").strip(),
        "has_assessment": str(source.get("has_assessment") or "").strip(),
        "has_lab_test": str(source.get("has_lab_test") or "").strip(),
        "doi": str(source.get("doi") or "").strip(),
        "pubmed_id": _join_values(source.get("pubmed_id")),
        "latest_data_release_version": str(source.get("latest_data_release_version") or "").strip(),
        "latest_data_release_date": str(source.get("latest_data_release_date") or "").strip(),
        "study_pi": _join_values(source.get("study_pi")),
        "gender_included": str(source.get("gender_included") or "").strip(),
        "sample_count": sample_count,
        "url": _study_url(accession),
        "_immport_source": source,
    }


def _supplemental_text_search_term(
    query: str,
    interpreted: InterpretedQuery | None,
) -> str | None:
    """Compact free-text term for the supplemental text_broad strategy."""
    if query.strip():
        compact = _compact_adhoc_search_term(query)
        if compact:
            return compact
    if interpreted:
        terms = [
            value
            for value in (
                interpreted.disease,
                interpreted.tissue,
                interpreted.assay,
            )
            if value
        ]
        if terms:
            return " ".join(terms)
    return None


def _resolve_search_queries(
    *,
    query: str,
    interpreted_query: InterpretedQuery | dict[str, Any] | None = None,
    concept_mappings: list[ConceptMapping] | None = None,
    include_text_broad: bool = True,
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
        queries = list(facet_queries)
        if include_text_broad:
            text_term = _supplemental_text_search_term(query, interpreted)
            if text_term:
                queries.append((TEXT_BROAD_STRATEGY, text_term))
        return queries
    if query.strip():
        compact = _compact_adhoc_search_term(query)
        return [("adhoc", compact or query.strip())]
    return []


def _strategy_has_remaining(
    strategy: str,
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
) -> bool:
    return strategy_offsets.get(strategy, 1) <= strategy_totals.get(strategy, 0)


def _compute_has_more(
    search_queries: list[tuple[str, str]],
    strategy_offsets: dict[str, int],
    strategy_totals: dict[str, int],
) -> bool:
    return any(
        _strategy_has_remaining(strategy, strategy_offsets, strategy_totals)
        for strategy, _ in search_queries
    )


def _count_all_immport_strategies(
    search_queries: list[tuple[str, str]],
    *,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | None,
) -> tuple[list[dict[str, str | int]], int, int, dict[str, int]]:
    """Run count-only ImmPort searches (pageSize=0) for every strategy."""
    strategy_summaries: list[dict[str, str | int]] = []
    strategy_totals: dict[str, int] = {}
    max_facet_total_found = 0
    primary_total_found = 0

    for index, (strategy, search_term) in enumerate(search_queries):
        try:
            params = _build_immport_search_params(
                search_term=search_term,
                concept_mappings=concept_mappings,
                interpreted=interpreted,
                strategy=strategy,
                page_size=0,
                from_record=1,
            )
            _, total_found = _immport_study_search(params)
            strategy_totals[strategy] = total_found
            if strategy in IMMPORT_FACET_STRATEGIES:
                max_facet_total_found = max(max_facet_total_found, total_found)
                if primary_total_found == 0:
                    primary_total_found = total_found
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": total_found,
                    "retrieved": 0,
                    "new_ids": 0,
                    "supplemental": strategy == TEXT_BROAD_STRATEGY,
                }
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("ImmPort count search failed for strategy %s: %s", strategy, exc)
            strategy_totals[strategy] = 0
            strategy_summaries.append(
                {
                    "strategy": strategy,
                    "search_term": search_term,
                    "total_found": 0,
                    "retrieved": 0,
                    "new_ids": 0,
                    "supplemental": strategy == TEXT_BROAD_STRATEGY,
                }
            )

    if max_facet_total_found == 0:
        max_facet_total_found = max(
            (
                total
                for strategy, total in strategy_totals.items()
                if strategy != TEXT_BROAD_STRATEGY
            ),
            default=0,
        )

    return strategy_summaries, max_facet_total_found, primary_total_found, strategy_totals


def _merge_immport_record(
    accession_to_record: dict[str, dict[str, Any]],
    accession_priority: dict[str, int],
    parsed: dict[str, Any],
    *,
    strategy: str,
    search_term: str,
) -> bool:
    """Insert or upgrade a parsed record; return True when a new accession was added."""
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


def _collect_immport_record_batch(
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
    """Collect the next batch of unseen ImmPort studies using strict-first paging."""
    accession_to_record: dict[str, dict[str, Any]] = {}
    accession_priority: dict[str, int] = {}
    updated_offsets = dict(strategy_offsets)
    batch_stats: list[dict[str, str | int]] = []

    for strategy, search_term in search_queries:
        retrieved = 0
        new_ids = 0
        from_record = updated_offsets.get(strategy, 1)
        total_for_strategy = strategy_totals.get(strategy, 0)

        while len(accession_to_record) < batch_size and from_record <= total_for_strategy:
            remaining_batch = batch_size - len(accession_to_record)
            remaining_strategy = total_for_strategy - from_record + 1
            page_size = min(per_strategy_page, remaining_batch, remaining_strategy)
            if page_size <= 0:
                break

            params = _build_immport_search_params(
                search_term=search_term,
                concept_mappings=concept_mappings,
                interpreted=interpreted,
                strategy=strategy,
                page_size=page_size,
                from_record=from_record,
            )
            entries, hit_count = _immport_study_search(params)
            strategy_totals[strategy] = hit_count
            total_for_strategy = hit_count
            retrieved += len(entries)

            if not entries:
                from_record = total_for_strategy + 1
                break

            for entry in entries:
                parsed = _parse_immport_record(entry)
                if not parsed:
                    continue
                if not _species_matches(species, parsed.get("species", "")):
                    continue
                if parsed["accession"] in seen_accessions:
                    continue
                if _merge_immport_record(
                    accession_to_record,
                    accession_priority,
                    parsed,
                    strategy=strategy,
                    search_term=search_term,
                ):
                    new_ids += 1
                if len(accession_to_record) >= batch_size:
                    break

            from_record += len(entries)

        updated_offsets[strategy] = from_record
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


def _build_immport_cursor(
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
        max_results=max_results,
        search_term=primary_search_term,
        repository=IMMPORT_REPOSITORY,
        include_text_broad=include_text_broad,
        has_more=_compute_has_more(search_queries, strategy_offsets, strategy_totals),
    )


def _build_source_metadata(record: dict[str, Any]) -> dict[str, str]:
    keys = (
        "research_focus",
        "program_name",
        "clinical_trial",
        "has_assessment",
        "has_lab_test",
        "doi",
        "pubmed_id",
        "latest_data_release_version",
        "latest_data_release_date",
        "study_pi",
        "gender_included",
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
    metadata["source"] = "ImmPort"
    metadata["access_profile"] = "open_or_registered"
    return metadata


def normalize_immport_record(
    record: dict[str, Any],
    *,
    retrieval_strategy: str | None = None,
    retrieval_search_term: str | None = None,
) -> DatasetCandidate | None:
    """Convert one ImmPort study record into a shared DatasetCandidate."""
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
        repository=IMMPORT_REPOSITORY,
        accession=accession,
        title=title,
        description=description,
        sample_count=record.get("sample_count"),
        url=str(record.get("url") or _study_url(accession)),
        metadata_fields=metadata_fields,
        observed_disease=str(record.get("condition_or_disease") or "").strip() or None,
        observed_tissue=str(record.get("biosample_type") or "").strip() or None,
        observed_assay=assay_method or None,
        observed_organism=str(record.get("species") or "").strip() or None,
        source_metadata=_build_source_metadata(record),
        retrieval_strategy=retrieval_strategy or record.get("_retrieval_strategy"),
        retrieval_search_term=retrieval_search_term or record.get("_retrieval_search_term"),
    )


def normalize_immport_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_immport_record(record)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_immport_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    include_text_broad: bool = True,
) -> dict[str, Any]:
    """Search ImmPort shared study metadata with multi-strategy facet queries."""
    max_results = get_immport_max_results(max_results)
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
            "max_results": max_results,
            "records": [],
            "source": "ImmPort",
            "repository": IMMPORT_REPOSITORY,
            "has_more": False,
            "load_more_cursor": None,
            "error": "No grounded concepts available for ImmPort search",
        }

    per_strategy_page = max(5, max_results)
    primary_search_term = search_queries[0][1]
    species = _species_from_interpreted(interpreted)
    errors: list[str] = []

    strategy_summaries, max_total_found, primary_total_found, strategy_totals = (
        _count_all_immport_strategies(
            search_queries,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
        )
    )

    seen_accessions: set[str] = set()
    strategy_offsets = {strategy: 1 for strategy, _ in search_queries}

    try:
        records, strategy_offsets, batch_stats = _collect_immport_record_batch(
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
        logger.warning("ImmPort search batch failed: %s", exc)
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

    cursor = _build_immport_cursor(
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

    retrievable_total = len(seen_accessions) if not cursor.has_more else None

    payload: dict[str, Any] = {
        "search_term": primary_search_term,
        "search_strategies": strategy_summaries,
        "total_found": max_total_found,
        "primary_total_found": primary_total_found,
        "retrievable_total": retrievable_total,
        "include_text_broad": include_text_broad,
        "max_results": max_results,
        "records": records[:max_results],
        "source": "ImmPort",
        "repository": IMMPORT_REPOSITORY,
        "has_more": cursor.has_more,
        "load_more_cursor": cursor.model_dump(),
    }
    if not records:
        payload["message"] = "No ImmPort studies matched the grounded search strategies"
    if errors:
        payload["warning"] = "; ".join(errors)
    return payload


def fetch_more_immport_repository_records(cursor: DatasetSearchCursor) -> dict[str, Any]:
    """Retrieve the next ImmPort batch using a saved load-more cursor."""
    concept_mappings = cursor.concept_mappings
    search_queries = _resolve_search_queries(
        query=cursor.query,
        interpreted_query=cursor.interpreted_query,
        concept_mappings=concept_mappings,
        include_text_broad=cursor.include_text_broad,
    )
    if not search_queries:
        return {
            "records": [],
            "added_count": 0,
            "has_more": False,
            "load_more_cursor": cursor.model_dump(),
            "error": "No grounded concepts available for ImmPort search",
        }

    per_strategy_page = max(5, cursor.max_results)
    primary_search_term = cursor.search_term or search_queries[0][1]
    seen_accessions = set(cursor.seen_accessions)
    strategy_offsets = dict(cursor.strategy_offsets)
    strategy_totals = dict(cursor.strategy_totals)
    species = _species_from_interpreted(cursor.interpreted_query)

    if not cursor.has_more:
        return {
            "records": [],
            "added_count": 0,
            "has_more": False,
            "load_more_cursor": cursor.model_dump(),
            "message": "No additional ImmPort records remain for this search",
        }

    try:
        records, strategy_offsets, _batch_stats = _collect_immport_record_batch(
            search_queries,
            batch_size=cursor.max_results,
            per_strategy_page=per_strategy_page,
            strategy_offsets=strategy_offsets,
            strategy_totals=strategy_totals,
            seen_accessions=seen_accessions,
            concept_mappings=concept_mappings,
            interpreted=cursor.interpreted_query,
            species=species,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("ImmPort load-more search failed: %s", exc)
        return {
            "records": [],
            "added_count": 0,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "error": f"ImmPort load-more failed: {exc}",
        }

    for record in records:
        seen_accessions.add(record["accession"])

    updated_cursor = _build_immport_cursor(
        concept_mappings=concept_mappings,
        search_queries=search_queries,
        strategy_offsets=strategy_offsets,
        strategy_totals=strategy_totals,
        seen_accessions=seen_accessions,
        max_results=cursor.max_results,
        total_found=cursor.total_found,
        primary_total_found=cursor.primary_total_found,
        primary_search_term=primary_search_term,
        query=cursor.query,
        interpreted_query=cursor.interpreted_query,
        include_text_broad=cursor.include_text_broad,
    )

    return {
        "records": records,
        "added_count": len(records),
        "has_more": updated_cursor.has_more,
        "load_more_cursor": updated_cursor.model_dump(),
        "total_found": cursor.total_found,
        "primary_total_found": cursor.primary_total_found,
        "retrievable_total": len(seen_accessions) if not updated_cursor.has_more else None,
        "include_text_broad": cursor.include_text_broad,
        "source": "ImmPort",
        "repository": IMMPORT_REPOSITORY,
    }


def search_immport_datasets(
    query: str,
    max_results: int | None = None,
    *,
    interpreted_query: dict[str, Any] | InterpretedQuery | None = None,
) -> dict[str, Any]:
    """Search ImmPort shared study metadata (tool entry point)."""
    interpreted = None
    if interpreted_query is not None:
        interpreted = (
            InterpretedQuery.model_validate(interpreted_query)
            if isinstance(interpreted_query, dict)
            else interpreted_query
        )

    search_result = fetch_immport_repository_records(
        concept_mappings=[],
        max_results=max_results,
        query=query,
        interpreted_query=interpreted,
    )

    results = []
    for record in search_result.get("records", []):
        item = dict(record)
        item.pop("_immport_source", None)
        item["retrieval_strategy"] = item.pop("_retrieval_strategy", None)
        item["retrieval_search_term"] = item.pop("_retrieval_search_term", None)
        results.append(item)

    payload: dict[str, Any] = {
        "query": query,
        "search_term": search_result.get("search_term", query),
        "search_strategies": search_result.get("search_strategies", []),
        "total_found": search_result.get("total_found", 0),
        "primary_total_found": search_result.get("primary_total_found", 0),
        "results": results,
        "source": "ImmPort",
    }
    if search_result.get("message"):
        payload["message"] = search_result["message"]
    if search_result.get("warning"):
        payload["warning"] = search_result["warning"]
    if search_result.get("error"):
        payload["error"] = search_result["error"]
    return payload
