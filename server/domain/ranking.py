"""Rank annotated dataset candidates by evidence coverage."""

from __future__ import annotations

from .dataset_search import ConceptMapping, DatasetCandidate
from .score_breakdown import build_score_breakdown

SLOT_WEIGHTS = {
    "disease": 0.30,
    "tissue": 0.25,
    "assay": 0.25,
    "organism": 0.10,
    "evidence_coverage": 0.10,
}


def rank_annotated_candidates(
    candidates: list[DatasetCandidate],
    concept_mappings: list[ConceptMapping],
) -> list[DatasetCandidate]:
    """
    Rank Results: score candidates that were already annotated with evidence.

    Scoring uses matched_concepts only — never requested facets without evidence.
    """
    expected_slots = {mapping.slot for mapping in concept_mappings}
    ranked: list[DatasetCandidate] = []

    for candidate in candidates:
        matched_slots = {mapping.slot for mapping in candidate.matched_concepts}
        slot_score = sum(
            SLOT_WEIGHTS[slot]
            for slot in matched_slots
            if slot in SLOT_WEIGHTS
        )
        covered = len(matched_slots & expected_slots)
        evidence_coverage = covered / len(expected_slots) if expected_slots else 0.0
        score = slot_score + (SLOT_WEIGHTS["evidence_coverage"] * evidence_coverage)

        if candidate.match_status == "model":
            match_status = "model"
        elif covered == len(expected_slots) and expected_slots:
            match_status = "full"
        else:
            match_status = "partial"

        score_breakdown = build_score_breakdown(
            candidate,
            concept_mappings,
            score=score,
            match_status=match_status,
            evidence_coverage=evidence_coverage,
        )
        ranked.append(
            candidate.model_copy(
                update={
                    "score": round(score, 3),
                    "match_status": match_status,
                    "score_breakdown": score_breakdown,
                }
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.accession))
    return ranked


def rank_dataset_candidates(
    candidates: list[DatasetCandidate],
    concept_mappings: list[ConceptMapping],
    requested_assay: str | None = None,
) -> list[DatasetCandidate]:
    """Backward-compatible wrapper: annotate then rank."""
    del requested_assay
    from .dataset_annotation import annotate_dataset_candidates

    annotated = annotate_dataset_candidates(candidates, concept_mappings)
    return rank_annotated_candidates(annotated, concept_mappings)
