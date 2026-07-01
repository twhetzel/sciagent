"""Build developer/debug score breakdowns for ranked dataset candidates."""

from __future__ import annotations

from .dataset_search import (
    ConceptMapping,
    DatasetCandidate,
    ScoreBreakdown,
    SlotEvidenceBreakdown,
    TissueEvidenceBreakdown,
)
from .evidence_extraction import (
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_organism_evidence_details,
    extract_tissue_evidence_details,
)


def build_score_breakdown(
    candidate: DatasetCandidate,
    concept_mappings: list[ConceptMapping],
    *,
    score: float,
    match_status: str,
    evidence_coverage: float,
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
    organism_present, organism_fields, organism_terms = extract_organism_evidence_details(
        mapping_by_slot.get("organism"),
        fields,
    )

    return ScoreBreakdown(
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
        organism=SlotEvidenceBreakdown(
            present=organism_present,
            fields=organism_fields,
            matched_terms=organism_terms,
        ),
        warnings_count=len(candidate.metadata_warnings),
        evidence_conflicts_count=len(candidate.evidence_conflicts),
        retrieval_strategy=candidate.retrieval_strategy,
        evidence_coverage=round(evidence_coverage, 3),
        final_score=round(score, 3),
        match_status=match_status,
    )
