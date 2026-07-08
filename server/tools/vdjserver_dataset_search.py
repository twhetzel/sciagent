"""VDJServer immune repertoire dataset search via the AIRR Data Commons API."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchCursor, InterpretedQuery
from domain.airr_assay import annotate_airr_metadata_fields
from domain.evidence_extraction import collect_metadata_fields
from domain.facet_abbreviation_resolution import QUERY_STOPWORDS
from domain.facet_search_strategies import STRATEGY_PRIORITY
from domain.text_broad_search import (
    TEXT_BROAD_STRATEGY,
    finalize_facet_total_found,
    resolve_search_queries_with_text_broad,
    roll_up_facet_totals,
    strategy_count_summary,
)
from domain.repository_vocab.vdjserver_vocab import (
    resolve_vdjserver_facet_value,
    vdjserver_assay_filter,
)

logger = logging.getLogger(__name__)

VDJSERVER_REPERTOIRE_URL = "https://vdjserver.org/airr/v1/repertoire"
VDJSERVER_REPOSITORY = "VDJServer"
VDJSERVER_SOURCE = "VDJServer AIRR API"
DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_CAP = 50
REQUEST_TIMEOUT = 20
MAX_PAGE_SIZE = 100

VDJSERVER_ADHOC_STOPWORDS = QUERY_STOPWORDS | frozenset(
    {
        "dataset",
        "datasets",
        "public",
        "immune",
        "repertoire",
        "repertoires",
        "vdjserver",
        "airr",
        "find",
        "sequencing",
    }
)

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")


def get_vdjserver_max_results(override: int | None = None) -> int:
    """Resolve result limit from explicit arg, env var, or default."""
    if override is not None:
        return max(1, min(int(override), MAX_RESULTS_CAP))

    raw = os.getenv("VDJSERVER_MAX_RESULTS", str(DEFAULT_MAX_RESULTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_RESULTS
    return max(1, min(value, MAX_RESULTS_CAP))


def _compact_adhoc_search_term(query: str) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in WORD_PATTERN.finditer(query):
        token = match.group()
        normalized = token.lower()
        if normalized in VDJSERVER_ADHOC_STOPWORDS or normalized in seen:
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
        "organism": by_slot.get("organism") or (interpreted.organism if interpreted else None),
    }


def _normalize_facet_value(slot: str, value: str | None) -> str | None:
    if not value:
        return None
    return resolve_vdjserver_facet_value(slot, value) or value.strip()


def _contains_filter(field: str, value: str) -> dict[str, Any]:
    return {"op": "contains", "content": {"field": field, "value": value}}


def _equals_filter(field: str, value: str) -> dict[str, Any]:
    return {"op": "=", "content": {"field": field, "value": value}}


def _combine_filters(clauses: list[dict[str, Any]]) -> dict[str, Any] | None:
    clauses = [clause for clause in clauses if clause]
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"op": "and", "content": clauses}


def build_vdjserver_adc_filters(
    *,
    strategy: str,
    search_term: str,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build one AIRR ADC filter object for a facet strategy."""
    facets = _facet_values(concept_mappings=concept_mappings, interpreted=interpreted)
    clauses: list[dict[str, Any]] = []

    organism = _normalize_facet_value("organism", facets.get("organism"))
    if organism:
        clauses.append(_equals_filter("subject.species.id", organism))

    if strategy == "adhoc":
        compact = _compact_adhoc_search_term(search_term)
        text = compact or search_term.strip()
        if text:
            clauses.append(_contains_filter("study.study_title", text))
        return _combine_filters(clauses)

    if strategy == TEXT_BROAD_STRATEGY:
        text = search_term.strip()
        if text:
            clauses.append(_contains_filter("study.study_title", text))
        return _combine_filters(clauses)

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
        if slot == "disease":
            clauses.append(_contains_filter("subject.diagnosis.disease_diagnosis.label", value))
        elif slot == "tissue":
            clauses.append(_contains_filter("sample.tissue.label", value))
        elif slot == "assay":
            assay_clause = vdjserver_assay_filter(value)
            if assay_clause:
                clauses.append(assay_clause)

    if not any(slot in slot_map for slot in ("disease", "tissue", "assay")) and search_term.strip():
        clauses.append(_contains_filter("study.study_title", search_term.strip()))

    return _combine_filters(clauses)


def _vdjserver_post(payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        VDJSERVER_REPERTOIRE_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _count_vdjserver_strategy(filters: dict[str, Any] | None) -> tuple[int, int]:
    """Return (unique_study_count, repertoire_row_count) for pagination and UI totals."""
    payload: dict[str, Any] = {"size": 0, "facets": ["study.study_id"]}
    if filters:
        payload["filters"] = filters
    data = _vdjserver_post(payload)
    facets = data.get("Facet") or []
    study_count = len(facets)
    repertoire_count = sum(int(item.get("count") or 0) for item in facets)
    return study_count, repertoire_count


def _fetch_vdjserver_repertoires(
    filters: dict[str, Any] | None,
    *,
    size: int,
    offset: int = 0,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "size": max(0, min(size, MAX_PAGE_SIZE)),
        "from": max(0, offset),
    }
    if filters:
        payload["filters"] = filters
    data = _vdjserver_post(payload)
    repertoires = data.get("Repertoire") or []
    if isinstance(repertoires, dict):
        return [repertoires]
    return list(repertoires)


def _join_labels(items: Any) -> str:
    if not items:
        return ""
    if isinstance(items, list):
        labels: list[str] = []
        for item in items:
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                if label:
                    labels.append(label)
            elif item:
                labels.append(str(item).strip())
        return ", ".join(dict.fromkeys(labels))
    if isinstance(items, dict):
        return str(items.get("label") or "").strip()
    return str(items).strip()


def _study_accession(study: dict[str, Any]) -> str:
    study_id = str(study.get("study_id") or "").strip()
    if study_id:
        if ":" in study_id:
            return study_id.split(":", maxsplit=1)[-1].strip()
        return study_id
    return str(study.get("vdjserver_uuid") or "").strip()


def _study_url(accession: str) -> str:
    if not accession:
        return "https://vdjserver.org/"
    upper = accession.upper()
    if upper.startswith("PRJ"):
        return f"https://www.ncbi.nlm.nih.gov/bioproject/{accession}"
    return "https://vdjserver.org/"


def _extract_disease_labels(subject: dict[str, Any]) -> str:
    diagnoses = subject.get("diagnosis") or []
    labels: list[str] = []
    for entry in diagnoses:
        if not isinstance(entry, dict):
            continue
        diagnosis = entry.get("disease_diagnosis") or {}
        label = str(diagnosis.get("label") or "").strip()
        if label:
            labels.append(label)
    return ", ".join(dict.fromkeys(labels))


def _extract_tissue_labels(samples: Any) -> str:
    if not samples:
        return ""
    if not isinstance(samples, list):
        samples = [samples]
    labels: list[str] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        tissue = _join_labels(sample.get("tissue"))
        sample_type = str(sample.get("sample_type") or "").strip()
        if tissue:
            labels.append(tissue)
        elif sample_type:
            labels.append(sample_type)
    return ", ".join(dict.fromkeys(labels))


def _extract_assay_labels(samples: Any, study: dict[str, Any]) -> str:
    labels: list[str] = []
    if not isinstance(samples, list):
        samples = [samples] if samples else []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        pcr_targets = sample.get("pcr_target") or []
        if not isinstance(pcr_targets, list):
            pcr_targets = [pcr_targets]
        for target in pcr_targets:
            if not isinstance(target, dict):
                continue
            locus = str(target.get("pcr_target_locus") or "").strip()
            if locus:
                labels.append(locus)
        platform = str(sample.get("sequencing_platform") or "").strip()
        if platform:
            labels.append(platform)
    keywords = study.get("keywords_study") or []
    if isinstance(keywords, list):
        labels.extend(str(item).strip() for item in keywords if str(item).strip())
    if labels:
        return ", ".join(dict.fromkeys(labels))
    return "AIRR-seq"


def _extract_species(subject: dict[str, Any]) -> str:
    species = subject.get("species") or {}
    if isinstance(species, dict):
        return _join_labels(species) or str(species.get("id") or "").strip()
    return str(species or "").strip()


def _parse_vdjserver_repertoire(repertoire: dict[str, Any]) -> dict[str, Any] | None:
    study = repertoire.get("study") or {}
    subject = repertoire.get("subject") or {}
    samples = repertoire.get("sample") or []
    accession = _study_accession(study)
    if not accession:
        return None

    title = str(study.get("study_title") or accession).strip()
    description = str(study.get("study_description") or "").strip()
    condition_or_disease = _extract_disease_labels(subject)
    biosample_type = _extract_tissue_labels(samples)
    assay_method = _extract_assay_labels(samples, study)
    species = _extract_species(subject)

    summary_parts = [part for part in (description, condition_or_disease, biosample_type, assay_method) if part]
    summary = ". ".join(summary_parts)

    sample_count = len(samples) if isinstance(samples, list) else 1

    return {
        "accession": accession,
        "title": title or accession,
        "description": description,
        "summary": summary,
        "condition_or_disease": condition_or_disease,
        "biosample_type": biosample_type,
        "assay_method": assay_method,
        "species": species,
        "url": _study_url(accession),
        "sample_count": sample_count,
        "study_id": str(study.get("study_id") or accession).strip(),
        "pub_ids": str(study.get("pub_ids") or "").strip(),
        "_vdjserver_source": repertoire,
    }


def _species_matches(species: str | None, record_species: str) -> bool:
    if not species:
        return True
    species_lower = species.lower()
    record_lower = (record_species or "").lower()
    if species_lower in {"human", "homo sapiens"}:
        return "homo sapiens" in record_lower or "9606" in record_lower or not record_lower
    if species_lower in {"mouse", "mus musculus"}:
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


def _count_all_vdjserver_strategies(
    search_queries: list[tuple[str, str]],
    *,
    concept_mappings: list[ConceptMapping] | None,
    interpreted: InterpretedQuery | None,
) -> tuple[list[dict[str, str | int]], int, int, dict[str, int]]:
    strategy_summaries: list[dict[str, str | int]] = []
    strategy_totals: dict[str, int] = {}
    strategy_study_totals: dict[str, int] = {}
    max_facet_total_found = 0
    primary_total_found = 0

    for _, (strategy, search_term) in enumerate(search_queries):
        try:
            filters = build_vdjserver_adc_filters(
                strategy=strategy,
                search_term=search_term,
                concept_mappings=concept_mappings,
                interpreted=interpreted,
            )
            study_count, repertoire_count = _count_vdjserver_strategy(filters)
            strategy_study_totals[strategy] = study_count
            strategy_totals[strategy] = repertoire_count
            max_facet_total_found, primary_total_found = roll_up_facet_totals(
                strategy,
                study_count,
                max_facet_total_found=max_facet_total_found,
                primary_total_found=primary_total_found,
            )
            strategy_summaries.append(
                strategy_count_summary(strategy, search_term, study_count)
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("VDJServer count search failed for strategy %s: %s", strategy, exc)
            strategy_study_totals[strategy] = 0
            strategy_totals[strategy] = 0
            strategy_summaries.append(strategy_count_summary(strategy, search_term, 0))

    max_total_found = finalize_facet_total_found(
        max_facet_total_found,
        strategy_study_totals,
    )
    return strategy_summaries, max_total_found, primary_total_found, strategy_totals


def _merge_vdjserver_record(
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


def _collect_vdjserver_record_batch(
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
        filters = build_vdjserver_adc_filters(
            strategy=strategy,
            search_term=search_term,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
        )

        while len(accession_to_record) < batch_size and offset < total_for_strategy:
            remaining_batch = batch_size - len(accession_to_record)
            page_size = min(per_strategy_page, remaining_batch * 3, MAX_PAGE_SIZE)
            if page_size <= 0:
                break

            entries = _fetch_vdjserver_repertoires(filters, size=page_size, offset=offset)
            retrieved += len(entries)

            if not entries:
                offset = total_for_strategy
                break

            for entry in entries:
                parsed = _parse_vdjserver_repertoire(entry)
                if not parsed:
                    continue
                if not _species_matches(species, parsed.get("species", "")):
                    continue
                if parsed["accession"] in seen_accessions:
                    continue
                if _merge_vdjserver_record(
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


def _text_broad_total_from_summaries(
    strategy_summaries: list[dict[str, str | int | bool]],
    *,
    include_text_broad: bool,
) -> int | None:
    if not include_text_broad:
        return None
    for summary in strategy_summaries:
        if summary.get("strategy") == TEXT_BROAD_STRATEGY:
            return int(summary.get("total_found") or 0)
    return None


def _build_vdjserver_cursor(
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
    text_broad_total_found: int | None = None,
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
        text_broad_total_found=text_broad_total_found,
        max_results=max_results,
        search_term=primary_search_term,
        repository=VDJSERVER_REPOSITORY,
        include_text_broad=include_text_broad,
        has_more=_compute_has_more(search_queries, strategy_offsets, strategy_totals),
    )


def _build_source_metadata(record: dict[str, Any]) -> dict[str, str]:
    keys = (
        "condition_or_disease",
        "biosample_type",
        "assay_method",
        "species",
        "study_id",
        "pub_ids",
    )
    metadata = {
        key: str(record.get(key)).strip()
        for key in keys
        if str(record.get(key) or "").strip()
    }
    metadata["source"] = VDJSERVER_SOURCE
    metadata["access_profile"] = "mixed"
    return metadata


def normalize_vdjserver_record(
    record: dict[str, Any],
    *,
    retrieval_strategy: str | None = None,
    retrieval_search_term: str | None = None,
) -> DatasetCandidate | None:
    """Convert one VDJServer study record into a shared DatasetCandidate."""
    accession = str(record.get("accession") or "").strip()
    if not accession:
        return None

    title = str(record.get("title") or "Untitled study").strip()
    description = str(record.get("description") or "").strip()
    summary = str(record.get("summary") or description).strip()
    assay_method = str(record.get("assay_method") or "AIRR-seq").strip()
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
    metadata_fields = annotate_airr_metadata_fields(metadata_fields, assay_method=assay_method)

    return DatasetCandidate(
        repository=VDJSERVER_REPOSITORY,
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


def normalize_vdjserver_records(records: list[dict[str, Any]]) -> list[DatasetCandidate]:
    candidates: list[DatasetCandidate] = []
    for record in records:
        candidate = normalize_vdjserver_record(record)
        if candidate:
            candidates.append(candidate)
    return candidates


def fetch_vdjserver_repository_records(
    concept_mappings: list[ConceptMapping],
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    include_text_broad: bool = True,
) -> dict[str, Any]:
    """Search VDJServer repertoire metadata with multi-strategy facet queries."""
    max_results = get_vdjserver_max_results(max_results)
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
            "source": VDJSERVER_SOURCE,
            "repository": VDJSERVER_REPOSITORY,
            "has_more": False,
            "load_more_cursor": None,
            "error": "No grounded concepts available for VDJServer search",
        }

    per_strategy_page = max(5, max_results)
    primary_search_term = search_queries[0][1]
    species = _species_from_interpreted(interpreted)
    errors: list[str] = []

    strategy_summaries, max_total_found, primary_total_found, strategy_totals = (
        _count_all_vdjserver_strategies(
            search_queries,
            concept_mappings=concept_mappings,
            interpreted=interpreted,
        )
    )

    seen_accessions: set[str] = set()
    strategy_offsets = {strategy: 0 for strategy, _ in search_queries}

    try:
        records, strategy_offsets, batch_stats = _collect_vdjserver_record_batch(
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
        logger.warning("VDJServer search batch failed: %s", exc)
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

    text_broad_total_found = _text_broad_total_from_summaries(
        strategy_summaries,
        include_text_broad=include_text_broad,
    )

    cursor = _build_vdjserver_cursor(
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
        text_broad_total_found=text_broad_total_found,
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
        "source": VDJSERVER_SOURCE,
        "repository": VDJSERVER_REPOSITORY,
        "has_more": cursor.has_more,
        "load_more_cursor": cursor.model_dump() if cursor.has_more else None,
    }
    if errors:
        payload["error"] = "; ".join(errors)
    return payload


def fetch_more_vdjserver_repository_records(cursor: DatasetSearchCursor) -> dict[str, Any]:
    """Load the next batch of VDJServer studies from cursor offsets."""
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
            "source": VDJSERVER_SOURCE,
            "repository": VDJSERVER_REPOSITORY,
            "error": "Cursor has no search strategies",
        }

    seen_accessions = set(cursor.seen_accessions)
    strategy_offsets = dict(cursor.strategy_offsets)
    strategy_totals = dict(cursor.strategy_totals)
    species = _species_from_interpreted(cursor.interpreted_query)

    try:
        records, strategy_offsets, _batch_stats = _collect_vdjserver_record_batch(
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
        logger.warning("VDJServer load-more batch failed: %s", exc)
        return {
            "records": [],
            "added_count": 0,
            "has_more": cursor.has_more,
            "load_more_cursor": cursor.model_dump(),
            "source": VDJSERVER_SOURCE,
            "repository": VDJSERVER_REPOSITORY,
            "error": str(exc),
        }

    for record in records:
        seen_accessions.add(record["accession"])

    updated_cursor = _build_vdjserver_cursor(
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
        text_broad_total_found=cursor.text_broad_total_found,
    )

    return {
        "records": records,
        "added_count": len(records),
        "has_more": updated_cursor.has_more,
        "load_more_cursor": updated_cursor.model_dump() if updated_cursor.has_more else None,
        "include_text_broad": cursor.include_text_broad,
        "text_broad_total_found": updated_cursor.text_broad_total_found,
        "source": VDJSERVER_SOURCE,
        "repository": VDJSERVER_REPOSITORY,
    }


def search_vdjserver_datasets(
    query: str,
    *,
    max_results: int | None = None,
    interpreted_query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Agent-facing VDJServer search wrapper."""
    payload = fetch_vdjserver_repository_records(
        [],
        max_results=max_results,
        query=query,
        interpreted_query=interpreted_query,
    )
    candidates = normalize_vdjserver_records(payload.get("records") or [])
    return {
        "results": [candidate.model_dump() for candidate in candidates],
        "total_found": payload.get("total_found", 0),
        "primary_total_found": payload.get("primary_total_found"),
        "search_term": payload.get("search_term"),
        "search_strategies": payload.get("search_strategies", []),
        "source": VDJSERVER_SOURCE,
        "repository": VDJSERVER_REPOSITORY,
        "has_more": payload.get("has_more", False),
        "load_more_cursor": payload.get("load_more_cursor"),
        "error": payload.get("error"),
    }
