"""Build developer/debug score breakdowns for ranked dataset candidates."""

from __future__ import annotations

from .dataset_search import (
    ConceptMapping,
    DatasetCandidate,
    OrganismEvidenceBreakdown,
    ScoreBreakdown,
    SlotEvidenceBreakdown,
    TissueEvidenceBreakdown,
)
from .evidence_extraction import (
    MIXED_ASSAY_LABEL,
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_organism_evidence_details,
    extract_tissue_evidence_details,
)


def determine_match_status(
    candidate: DatasetCandidate,
    *,
    expected_slot_count: int,
    covered_slot_count: int,
    breakdown: ScoreBreakdown,
) -> str:
    """
    Assign auditable match status from evidence coverage and quality signals.

    Does not change the numeric score — only refines the status label so
    overconfident "full" results are avoided when metadata is ambiguous.
    """
    is_animal_model = candidate.match_status == "model"
    mixed_assay = candidate.observed_assay == MIXED_ASSAY_LABEL
    tissue_ambiguous = breakdown.tissue.evidence_type in {"derived_model", "ambiguous"}

    if is_animal_model or mixed_assay or tissue_ambiguous:
        return "ambiguous_or_mixed"

    if not expected_slot_count or covered_slot_count < expected_slot_count:
        return "partial"

    organism_narrative_only = (
        breakdown.organism.present and breakdown.organism.evidence_source == "narrative"
    )
    has_warnings = bool(candidate.metadata_warnings)
    has_conflicts = bool(candidate.evidence_conflicts)

    if has_warnings or has_conflicts or organism_narrative_only:
        return "full_with_warnings"

    return "full"


def build_score_breakdown(
    candidate: DatasetCandidate,
    concept_mappings: list[ConceptMapping],
    *,
    score: float,
    evidence_coverage: float,
    expected_slot_count: int,
    covered_slot_count: int,
) -> ScoreBreakdown:
    """Assemble an auditable breakdown of ranking inputs for one candidate."""
    mapping_by_slot = {mapping.slot: mapping for mapping in concept_mappings}
    fields = candidate.metadata_fields or {
        "title": candidate.title,
        "summary": candidate.description,
    }

    disease_present, disease_fields, disease_terms = extract_disease_evidence_details(
        mapping_by_slot.get("disease"),
        fields,
    )
    tissue_present, tissue_fields, tissue_terms, tissue_type = extract_tissue_evidence_details(
        mapping_by_slot.get("tissue"),
        fields,
    )
    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(
        mapping_by_slot.get("assay"),
        fields,
    )
    organism_present, organism_fields, organism_terms, organism_source = (
        extract_organism_evidence_details(
            mapping_by_slot.get("organism"),
            fields,
        )
    )

    breakdown = ScoreBreakdown(
        disease=SlotEvidenceBreakdown(
            present=disease_present,
            fields=disease_fields,
            matched_terms=disease_terms,
        ),
        tissue=TissueEvidenceBreakdown(
            present=tissue_present,
            fields=tissue_fields,
            matched_terms=tissue_terms,
            evidence_type=tissue_type,
        ),
        assay=SlotEvidenceBreakdown(
            present=assay_present,
            fields=assay_fields,
            matched_terms=assay_terms,
        ),
        organism=OrganismEvidenceBreakdown(
            present=organism_present,
            fields=organism_fields,
            matched_terms=organism_terms,
            evidence_source=organism_source,
        ),
        warnings=list(candidate.metadata_warnings),
        evidence_conflicts=list(candidate.evidence_conflicts),
        warnings_count=len(candidate.metadata_warnings),
        evidence_conflicts_count=len(candidate.evidence_conflicts),
        retrieval_strategy=candidate.retrieval_strategy,
        evidence_coverage=round(evidence_coverage, 3),
        evidence_score=round(score, 3),
        match_status="partial",
    )
    breakdown.match_status = determine_match_status(
        candidate,
        expected_slot_count=expected_slot_count,
        covered_slot_count=covered_slot_count,
        breakdown=breakdown,
    )
    return breakdown
