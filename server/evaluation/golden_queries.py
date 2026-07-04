"""
Golden-query evaluation harness for the dataset discovery pipeline.

Runs representative natural-language queries against enabled dataset sources and
captures structured metrics for regression review. Developer-facing only.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any

from agent.dataset_discovery import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    _build_dataset_search_result,
    annotate_evidence,
    ground_query,
    interpret_query,
    merge_repository_search_results,
    normalize_merged_records,
    normalize_records,
    rank_results,
    resolve_max_results,
    search_repository,
)
from domain.assay_ranking import validate_rna_seq_assay_ranking
from domain.dataset_context_export import export_dataset_search_agent_context
from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchResult
from domain.ranking import assert_monotonic_rank_scores
from sciagent_server.config import get_ncbi_email, is_source_enabled

GOLDEN_QUERIES: tuple[str, ...] = (
    "Find public RNA-seq datasets for ulcerative colitis colon tissue.",
    "Find public RNA-seq datasets for UC colon tissue.",
    "Find public RNA-seq datasets for Crohn's disease ileum tissue.",
    "Find public RNA-seq datasets for Alzheimer's disease brain tissue.",
)

TOP_N = 10
DEFAULT_GOLDEN_MAX_RESULTS = 10
DEFAULT_QUERY_PAUSE_SEC = 2.0


def resolve_enabled_dataset_repositories() -> list[str]:
    """Return dataset repositories enabled via SCIAGENT_EXCLUDED_SOURCES."""
    repositories: list[str] = []
    if is_source_enabled("geo_dataset_search"):
        repositories.append(GEO_REPOSITORY)
    if is_source_enabled("expression_atlas"):
        repositories.append(GXA_REPOSITORY)
    return repositories


def _concept_summary(mapping: ConceptMapping) -> dict[str, Any]:
    summary = {
        "slot": mapping.slot,
        "query_term": mapping.query_term,
        "label": mapping.label,
        "curie": mapping.curie,
        "ontology": mapping.ontology,
        "match_type": mapping.match_type,
        "source": mapping.source,
        "confidence": mapping.confidence,
    }
    if mapping.selection_reason:
        summary["selection_reason"] = mapping.selection_reason
    if mapping.rejected_candidates:
        summary["rejected_candidates"] = mapping.rejected_candidates
    return summary


def _candidate_summary(candidate: DatasetCandidate, rank: int) -> dict[str, Any]:
    breakdown = candidate.score_breakdown
    evidence_score = breakdown.evidence_score if breakdown is not None else candidate.score
    return {
        "rank": rank,
        "accession": candidate.accession,
        "title": candidate.title,
        "repository": candidate.repository,
        "display_rank_score": round(candidate.score, 4),
        "evidence_score": round(evidence_score, 4),
        "rank_tier": breakdown.rank_tier if breakdown is not None else None,
        "match_tier": breakdown.match_tier if breakdown is not None else None,
        "partial_assay_subtype": breakdown.partial_assay_subtype if breakdown is not None else None,
        "base_score": round(breakdown.base_score, 4) if breakdown is not None else None,
        "quality_adjustment": round(breakdown.quality_adjustment, 4) if breakdown is not None else None,
        "score": round(candidate.score, 4),
        "match_status": candidate.match_status,
        "assay_mismatch": candidate.assay_mismatch,
        "retrieval_strategy": candidate.retrieval_strategy,
        "warnings_count": len(candidate.metadata_warnings),
        "conflicts_count": len(candidate.evidence_conflicts),
    }


def _count_warnings_and_conflicts(candidates: list[DatasetCandidate]) -> tuple[int, int]:
    warnings = sum(len(candidate.metadata_warnings) for candidate in candidates)
    conflicts = sum(len(candidate.evidence_conflicts) for candidate in candidates)
    return warnings, conflicts


def _try_context_export(result: DatasetSearchResult) -> tuple[bool, str | None]:
    try:
        exported = export_dataset_search_agent_context(result)
    except Exception as exc:  # noqa: BLE001 — capture export failures for the harness
        return False, str(exc)
    if not exported.get("markdown") or not exported.get("json"):
        return False, "export missing markdown or json payload"
    return True, None


def _warn_if_ncbi_misconfigured() -> None:
    if not get_ncbi_email():
        print(
            "Warning: NCBI_EMAIL is not set; NCBI may return HTTP 429 during multi-query runs. "
            "Set NCBI_EMAIL (and optionally NCBI_API_KEY) in .env. "
            "PUBMED_EMAIL is still accepted as a fallback.",
            flush=True,
        )


def evaluate_golden_query(
    query: str,
    *,
    repositories: list[str] | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    """
    Run one golden query through the dataset discovery pipeline and return metrics.

    Per-source repository searches are executed individually so hit counts remain
    attributable before merge/deduplication.
    """
    enabled = repositories if repositories is not None else resolve_enabled_dataset_repositories()
    effective_max_results = (
        max_results if max_results is not None else DEFAULT_GOLDEN_MAX_RESULTS
    )
    report: dict[str, Any] = {
        "query": query,
        "enabled_sources": enabled,
        "max_results": effective_max_results,
    }

    if not enabled:
        report["error"] = "No dataset sources enabled (check SCIAGENT_EXCLUDED_SOURCES)"
        report["context_export_ok"] = False
        return report

    interpreted = interpret_query(query)
    report["interpreted_facets"] = interpreted.model_dump()

    concept_mappings = ground_query(interpreted)
    report["grounded_concepts"] = [_concept_summary(mapping) for mapping in concept_mappings]

    search_results: list[dict] = []
    per_source_hit_counts: dict[str, int] = {}
    for repository in enabled:
        search_result = search_repository(
            repository,
            concept_mappings,
            max_results=resolve_max_results(repository, effective_max_results),
            query=query,
            interpreted_query=interpreted,
        )
        search_results.append(search_result)
        per_source_hit_counts[repository] = int(search_result.get("total_found") or 0)

    report["per_source_hit_counts"] = per_source_hit_counts

    if len(search_results) == 1:
        merged_search = search_results[0]
        repo_label = enabled[0]
        candidates = normalize_records(repo_label, merged_search.get("records", []))
    else:
        merged_search = merge_repository_search_results(search_results)
        repo_label = merged_search.get("repository", " + ".join(enabled))
        candidates = normalize_merged_records(merged_search.get("records", []))

    annotated = annotate_evidence(candidates, concept_mappings)
    ranked = rank_results(annotated, concept_mappings)
    result = _build_dataset_search_result(
        query=query,
        interpreted=interpreted,
        concept_mappings=concept_mappings,
        ranked=ranked,
        search_result=merged_search,
        repository=repo_label,
    )

    top = ranked[:TOP_N]
    assert_monotonic_rank_scores(top)
    assay_ranking_violations = validate_rna_seq_assay_ranking(
        concept_mappings,
        ranked,
        top_n=TOP_N,
    )
    report["assay_ranking_violations"] = assay_ranking_violations
    report["assay_ranking_ok"] = len(assay_ranking_violations) == 0
    report["top_10"] = [_candidate_summary(candidate, rank) for rank, candidate in enumerate(top, start=1)]
    report["top_10_source_distribution"] = dict(Counter(candidate.repository for candidate in top))
    report["match_statuses"] = dict(Counter(candidate.match_status for candidate in top))

    warnings_count, conflicts_count = _count_warnings_and_conflicts(top)
    report["warnings_count"] = warnings_count
    report["conflicts_count"] = conflicts_count

    context_export_ok, context_export_error = _try_context_export(result)
    report["context_export_ok"] = context_export_ok
    if context_export_error:
        report["context_export_error"] = context_export_error

    report["integrated_total_found"] = result.total_found
    report["integrated_retrieved_count"] = result.retrieved_count
    report["search_strategies"] = result.search_strategies

    return report


def evaluate_all_golden_queries(
    queries: tuple[str, ...] | list[str] | None = None,
    *,
    pause_between_queries_sec: float = DEFAULT_QUERY_PAUSE_SEC,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Evaluate each golden query and return a list of metric reports."""
    _warn_if_ncbi_misconfigured()
    selected = list(queries or GOLDEN_QUERIES)
    reports: list[dict[str, Any]] = []
    for index, query in enumerate(selected):
        if index and pause_between_queries_sec > 0:
            time.sleep(pause_between_queries_sec)
        reports.append(evaluate_golden_query(query, **kwargs))
    return reports


def format_report_text(report: dict[str, Any]) -> str:
    """Render one evaluation report as human-readable text."""
    lines = [
        f"Query: {report.get('query', '')}",
        f"Enabled sources: {', '.join(report.get('enabled_sources') or []) or '(none)'}",
    ]

    if report.get("error"):
        lines.append(f"Error: {report['error']}")
        return "\n".join(lines)

    facets = report.get("interpreted_facets") or {}
    facet_parts = [f"{slot}={value}" for slot, value in facets.items() if value]
    lines.append(f"Interpreted facets: {', '.join(facet_parts) or '(none)'}")

    concepts = report.get("grounded_concepts") or []
    if concepts:
        lines.append("Grounded concepts:")
        for concept in concepts:
            lines.append(
                f"  - {concept['slot']}: {concept['label']} ({concept['curie']}) "
                f"[{concept['match_type']}, {concept['source']}, {concept['confidence']:.2f}]"
            )
            if concept.get("selection_reason"):
                lines.append(f"    selection: {concept['selection_reason']}")
            for rejected in concept.get("rejected_candidates") or []:
                lines.append(
                    f"    rejected: {rejected.get('label')} ({rejected.get('curie')}) "
                    f"[{rejected.get('ontology')}, tier={rejected.get('ontology_tier')}]"
                )
    else:
        lines.append("Grounded concepts: (none)")

    hit_counts = report.get("per_source_hit_counts") or {}
    lines.append(
        "Per-source hit counts: "
        + ", ".join(f"{repo}={count:,}" for repo, count in hit_counts.items())
    )
    lines.append(
        f"Integrated retrieved: {report.get('integrated_retrieved_count', 0):,} "
        f"(total_found={report.get('integrated_total_found', 0):,})"
    )

    distribution = report.get("top_10_source_distribution") or {}
    lines.append(
        "Top 10 source distribution: "
        + ", ".join(f"{repo}={count}" for repo, count in sorted(distribution.items()))
        or "(none)"
    )

    statuses = report.get("match_statuses") or {}
    lines.append(
        "Top 10 match statuses: "
        + ", ".join(f"{status}={count}" for status, count in sorted(statuses.items()))
        or "(none)"
    )
    lines.append(
        f"Top 10 warnings/conflicts: {report.get('warnings_count', 0)}/{report.get('conflicts_count', 0)}"
    )
    lines.append(f"Context export OK: {report.get('context_export_ok', False)}")

    violations = report.get("assay_ranking_violations") or []
    if violations:
        lines.append("Assay ranking violations:")
        for violation in violations:
            lines.append(f"  - {violation}")
    else:
        lines.append("Assay ranking violations: (none)")
    lines.append(f"Assay ranking OK: {report.get('assay_ranking_ok', True)}")

    top_10 = report.get("top_10") or []
    if top_10:
        lines.append(
            "Top 10 integrated results (sorted by display_rank_score = rank_tier × 10 + evidence_score):"
        )
        for item in top_10:
            rank_tier = item.get("rank_tier", item.get("match_tier"))
            tier_label = f"rank_tier={rank_tier} " if rank_tier is not None else ""
            subtype = item.get("partial_assay_subtype")
            subtype_label = f"subtype={subtype} " if subtype else ""
            lines.append(
                f"  {item['rank']}. {item['accession']} ({item['repository']}) "
                f"display_rank_score={item.get('display_rank_score', item['score'])} "
                f"evidence_score={item.get('evidence_score', item['score'])} "
                f"{tier_label}{subtype_label}status={item['match_status']}"
                f"{' assay_mismatch' if item.get('assay_mismatch') else ''} — {item['title'][:80]}"
            )
    else:
        lines.append("Top 10 integrated results: (none)")

    return "\n".join(lines)
