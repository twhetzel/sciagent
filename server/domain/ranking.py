"""Rank annotated dataset candidates by evidence coverage."""

from __future__ import annotations

from .assay_ranking import compute_assay_rank_adjustment, compute_rank_tier, explain_rank_tier
from .dataset_search import ConceptMapping, DatasetCandidate
from .facet_match_quality import (
    compute_display_rank_score,
    compute_facet_quality_adjustment,
    ranking_sort_key,
)
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
    Facet-quality adjustments prefer exact disease, requested assay, and direct tissue
    matches while keeping partial results in the ranked list.
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
        base_score = slot_score + (SLOT_WEIGHTS["evidence_coverage"] * evidence_coverage)

        score_breakdown = build_score_breakdown(
            candidate,
            concept_mappings,
            score=base_score,
            evidence_coverage=evidence_coverage,
            expected_slot_count=len(expected_slots),
            covered_slot_count=covered,
        )
        match_status = score_breakdown.match_status
        base_score = round(base_score, 3)
        assay_mapping = next((mapping for mapping in concept_mappings if mapping.slot == "assay"), None)
        quality_adjustment = compute_facet_quality_adjustment(
            candidate,
            score_breakdown,
            concept_mappings,
        )
        assay_rank_adjustment, assay_mismatch, assay_mismatch_note = compute_assay_rank_adjustment(
            candidate,
            score_breakdown,
            assay_mapping,
            match_status=match_status,
        )
        evidence_score = round(
            max(0.0, base_score + quality_adjustment + assay_rank_adjustment),
            3,
        )
        rank_tier, partial_assay_subtype = compute_rank_tier(
            match_status,
            assay_mapping,
            candidate,
            score_breakdown,
            assay_mismatch,
        )
        display_rank_score = compute_display_rank_score(evidence_score, rank_tier)
        tier_note = explain_rank_tier(match_status, rank_tier, partial_assay_subtype)
        score_breakdown = score_breakdown.model_copy(
            update={
                "base_score": base_score,
                "quality_adjustment": quality_adjustment,
                "assay_rank_adjustment": assay_rank_adjustment,
                "evidence_score": evidence_score,
                "rank_tier": rank_tier,
                "match_tier": rank_tier,
                "partial_assay_subtype": partial_assay_subtype,
                "display_rank_score": display_rank_score,
                "match_tier_note": tier_note,
                "requested_assay": assay_mapping.label if assay_mapping else None,
                "observed_assay": candidate.observed_assay,
                "assay_mismatch": assay_mismatch,
                "assay_mismatch_note": assay_mismatch_note,
            },
        )

        ranked.append(
            candidate.model_copy(
                update={
                    "score": display_rank_score,
                    "match_status": match_status,
                    "assay_mismatch": assay_mismatch,
                    "score_breakdown": score_breakdown,
                }
            )
        )

    ranked.sort(key=ranking_sort_key)
    return ranked


def assert_monotonic_display_rank_scores(candidates: list[DatasetCandidate]) -> None:
    """Raise AssertionError when integrated results are not sorted by display_rank_score."""
    for index in range(len(candidates) - 1):
        current = candidates[index].score
        following = candidates[index + 1].score
        if current < following:
            raise AssertionError(
                f"display_rank_score not monotonic at positions {index + 1} and {index + 2}: "
                f"{candidates[index].accession}={current} < "
                f"{candidates[index + 1].accession}={following}"
            )


def assert_monotonic_rank_scores(candidates: list[DatasetCandidate]) -> None:
    """Backward-compatible alias for assert_monotonic_display_rank_scores."""
    assert_monotonic_display_rank_scores(candidates)


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
