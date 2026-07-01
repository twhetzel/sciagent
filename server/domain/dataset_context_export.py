"""Agent-ready context export for dataset discovery results."""

from __future__ import annotations

from typing import Any

from .dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchResult

BASE_DOWNSTREAM_CAUTION = (
    "Inspect sample-level metadata before assuming case/control design."
)


def _concept_to_dict(mapping: ConceptMapping) -> dict[str, Any]:
    return {
        "slot": mapping.slot,
        "query_term": mapping.query_term,
        "label": mapping.label,
        "curie": mapping.curie,
        "iri": mapping.iri,
        "ontology": mapping.ontology,
        "synonyms": mapping.synonyms,
        "match_type": mapping.match_type,
        "source": mapping.source,
        "confidence": mapping.confidence,
        "explanation": mapping.explanation,
    }


def _candidate_to_dict(candidate: DatasetCandidate, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "accession": candidate.accession,
        "title": candidate.title,
        "repository": candidate.repository,
        "url": candidate.url,
        "score": candidate.score,
        "match_status": candidate.match_status,
        "retrieval_strategy": candidate.retrieval_strategy,
        "retrieval_search_term": candidate.retrieval_search_term,
        "sample_count": candidate.sample_count,
        "observed_metadata": {
            "disease": candidate.observed_disease,
            "tissue": candidate.observed_tissue,
            "assay": candidate.observed_assay,
            "organism": candidate.observed_organism,
        },
        "matched_concepts": [_concept_to_dict(m) for m in candidate.matched_concepts],
        "evidence_snippets": [
            {
                "field": snippet.field,
                "text": snippet.text,
                "matched_concepts": snippet.matched_concepts,
            }
            for snippet in candidate.evidence_snippets
        ],
        "why_matched": candidate.why_matched,
        "why_partial": candidate.why_partial,
        "metadata_warnings": candidate.metadata_warnings,
        "evidence_conflicts": candidate.evidence_conflicts,
        "score_breakdown": (
            candidate.score_breakdown.model_dump() if candidate.score_breakdown else None
        ),
    }


def build_downstream_cautions(result: DatasetSearchResult) -> list[str]:
    """Suggest follow-up checks before downstream analysis or reuse."""
    cautions = [BASE_DOWNSTREAM_CAUTION]

    if not result.candidates:
        cautions.append(
            "No ranked candidates were returned; broaden search terms or verify ontology grounding."
        )
        return cautions

    partial_count = sum(1 for c in result.candidates if c.match_status == "partial")
    if partial_count:
        cautions.append(
            f"{partial_count} ranked candidate(s) are partial matches; confirm unsupported facets in sample metadata."
        )

    if any(c.evidence_conflicts for c in result.candidates):
        cautions.append(
            "Evidence conflicts were detected across metadata fields; review conflicting fields manually."
        )

    if any(c.observed_assay == "mixed or multi-assay" for c in result.candidates):
        cautions.append(
            "Some datasets appear mixed or multi-assay; do not assume a single assay without per-sample review."
        )

    assay_requested = any(m.slot == "assay" for m in result.concept_mappings)
    if assay_requested and any(
        not any(m.slot == "assay" for m in c.matched_concepts) for c in result.candidates
    ):
        cautions.append(
            "Requested assay was not supported by metadata evidence for at least one ranked dataset."
        )

    if any(c.match_status == "model" for c in result.candidates):
        cautions.append(
            "Some ranked datasets are animal model studies; do not treat them as direct human clinical data."
        )

    if result.total_found > len(result.candidates):
        cautions.append(
            f"Only {len(result.candidates)} of {result.total_found} repository hits were ranked; additional candidates may exist."
        )

    return cautions

def export_dataset_search_json(result: DatasetSearchResult) -> dict[str, Any]:
    """Structured JSON context for downstream agents."""
    interpreted = result.interpreted_query
    return {
        "type": "dataset_discovery",
        "version": "1.0",
        "query": result.query,
        "interpreted_facets": {
            "disease": interpreted.disease,
            "tissue": interpreted.tissue,
            "assay": interpreted.assay,
            "organism": interpreted.organism,
        },
        "grounded_concepts": [_concept_to_dict(m) for m in result.concept_mappings],
        "search": {
            "repository": result.repository,
            "source": result.source,
            "search_term": result.search_term,
            "search_strategies": result.search_strategies,
            "total_found": result.total_found,
            "ranked_count": len(result.candidates),
        },
        "downstream_cautions": build_downstream_cautions(result),
        "candidates": [
            _candidate_to_dict(candidate, rank)
            for rank, candidate in enumerate(result.candidates, start=1)
        ],
    }


def _format_concept_line(mapping: ConceptMapping) -> str:
    return (
        f"- **{mapping.slot}**: {mapping.label} (`{mapping.curie}`) "
        f"— query term: {mapping.query_term}; source: {mapping.source}; "
        f"match: {mapping.match_type}; confidence: {mapping.confidence:.2f}"
    )


def _format_candidate_markdown(candidate: DatasetCandidate, rank: int) -> str:
    lines = [
        f"### {rank}. {candidate.accession} — {candidate.title}",
        "",
        f"- **Repository**: {candidate.repository}",
    ]
    if candidate.url:
        lines.append(f"- **URL**: {candidate.url}")
    lines.append(
        f"- **Score**: {candidate.score:.3f} | **Match status**: {candidate.match_status}"
    )
    if candidate.retrieval_strategy:
        lines.append(f"- **Retrieval strategy**: {candidate.retrieval_strategy}")
    if candidate.retrieval_search_term:
        lines.append(f"- **Retrieval query**: `{candidate.retrieval_search_term}`")
    if candidate.sample_count is not None:
        lines.append(f"- **Sample count**: {candidate.sample_count}")

    lines.extend(
        [
            "- **Observed metadata**:",
            f"  - disease: {candidate.observed_disease or 'unknown'}",
            f"  - tissue: {candidate.observed_tissue or 'unknown'}",
            f"  - assay: {candidate.observed_assay or 'unknown'}",
            f"  - organism: {candidate.observed_organism or 'unknown'}",
        ]
    )

    if candidate.matched_concepts:
        lines.append("- **Matched concepts**:")
        for mapping in candidate.matched_concepts:
            lines.append(f"  - {mapping.slot}: {mapping.label} ({mapping.curie})")

    if candidate.why_matched:
        lines.append("- **Why matched**:")
        for reason in candidate.why_matched:
            lines.append(f"  - {reason}")

    if candidate.why_partial:
        lines.append("- **Why partial**:")
        for reason in candidate.why_partial:
            lines.append(f"  - {reason}")

    if candidate.metadata_warnings:
        lines.append("- **Metadata warnings**:")
        for warning in candidate.metadata_warnings:
            lines.append(f"  - {warning}")

    if candidate.evidence_conflicts:
        lines.append("- **Evidence conflicts**:")
        for conflict in candidate.evidence_conflicts:
            lines.append(f"  - {conflict}")

    if candidate.score_breakdown:
        breakdown = candidate.score_breakdown
        lines.append("- **Score breakdown (debug)**:")
        lines.append(f"  - final score: {breakdown.final_score:.3f}")
        lines.append(f"  - match status: {breakdown.match_status}")
        lines.append(f"  - evidence coverage: {breakdown.evidence_coverage:.3f}")
        if breakdown.retrieval_strategy:
            lines.append(f"  - retrieval strategy: {breakdown.retrieval_strategy}")
        lines.append(f"  - warnings: {breakdown.warnings_count}")
        lines.append(f"  - evidence conflicts: {breakdown.evidence_conflicts_count}")
        for slot in ("disease", "tissue", "assay", "organism"):
            slot_breakdown = getattr(breakdown, slot)
            status = "present" if slot_breakdown.present else "absent"
            fields = ", ".join(slot_breakdown.fields) if slot_breakdown.fields else "—"
            terms = ", ".join(slot_breakdown.matched_terms) if slot_breakdown.matched_terms else "—"
            line = f"  - {slot}: {status}; fields: {fields}; terms: {terms}"
            if slot == "tissue" and hasattr(slot_breakdown, "evidence_type"):
                line += f"; tissue type: {slot_breakdown.evidence_type}"
            lines.append(line)

    if candidate.evidence_snippets:
        lines.append("- **Evidence snippets**:")
        for snippet in candidate.evidence_snippets:
            concept_note = ""
            if snippet.matched_concepts:
                concept_note = f" (matched: {', '.join(snippet.matched_concepts)})"
            lines.append(f"  - `{snippet.field}`: {snippet.text}{concept_note}")

    return "\n".join(lines)


def export_dataset_search_markdown(result: DatasetSearchResult) -> str:
    """Markdown context for downstream agents."""
    interpreted = result.interpreted_query
    lines = [
        "# Dataset discovery agent context",
        "",
        "## User query",
        result.query,
        "",
        "## Interpreted facets",
    ]

    facet_lines = []
    for slot in ("disease", "tissue", "assay", "organism"):
        value = getattr(interpreted, slot)
        if value:
            facet_lines.append(f"- **{slot}**: {value}")
    lines.extend(facet_lines or ["- *(no structured facets extracted)*"])
    lines.append("")

    lines.append("## Grounded ontology concepts")
    if result.concept_mappings:
        lines.extend(_format_concept_line(mapping) for mapping in result.concept_mappings)
    else:
        lines.append("- *(none)*")
    lines.append("")

    lines.extend(
        [
            "## Search",
            f"- **Repository searched**: {result.repository} ({result.source})",
        ]
    )
    if result.search_term:
        lines.append(f"- **Primary search term**: `{result.search_term}`")
    if result.search_strategies:
        lines.append("- **Search strategies**:")
        for item in result.search_strategies:
            lines.append(
                f"  - {item.get('strategy')}: `{item.get('search_term')}` "
                f"({item.get('total_found', 0)} hits, retrieved {item.get('retrieved', 0)})"
            )
    lines.append(f"- **Total repository hits**: {result.total_found}")
    lines.append(f"- **Ranked candidates**: {len(result.candidates)}")
    lines.append("")

    cautions = build_downstream_cautions(result)
    lines.append("## Downstream cautions")
    lines.extend(f"- {caution}" for caution in cautions)
    lines.append("")

    lines.append("## Ranked dataset candidates")
    if result.candidates:
        for rank, candidate in enumerate(result.candidates, start=1):
            lines.append(_format_candidate_markdown(candidate, rank))
            lines.append("")
    else:
        lines.append("*(no ranked candidates)*")

    return "\n".join(lines).rstrip() + "\n"


def export_dataset_search_agent_context(result: DatasetSearchResult) -> dict[str, Any]:
    """Export both markdown and JSON agent-ready context."""
    return {
        "markdown": export_dataset_search_markdown(result),
        "json": export_dataset_search_json(result),
    }
