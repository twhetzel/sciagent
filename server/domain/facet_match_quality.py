"""Facet-specific ranking adjustments for dataset discovery."""

from __future__ import annotations

from .dataset_search import ConceptMapping, DatasetCandidate, ScoreBreakdown
from .synonym_classification import _normalize_text, term_in_text

MATCH_STATUS_ORDER: dict[str, int] = {
    "full": 4,
    "full_with_warnings": 3,
    "partial": 2,
    "ambiguous_or_mixed": 1,
    "model": 1,
}

# Status tier must dominate facet relevance scores (typically <= ~1.5).
STATUS_TIER_WEIGHT = 10.0

DISEASE_RELATED_TERMS: dict[str, frozenset[str]] = {
    "ulcerative colitis": frozenset(
        {
            "crohn's disease",
            "crohn disease",
            "crohns disease",
            "regional enteritis",
            "inflammatory bowel disease",
            "ibd",
        }
    ),
    "crohn's disease": frozenset(
        {
            "ulcerative colitis",
            "colitis ulcerative",
            "inflammatory bowel disease",
            "ibd",
        }
    ),
    "crohn disease": frozenset(
        {
            "ulcerative colitis",
            "colitis ulcerative",
            "inflammatory bowel disease",
            "ibd",
        }
    ),
}

TISSUE_EVIDENCE_ADJUSTMENTS: dict[str, float] = {
    "direct": 0.06,
    "ambiguous": -0.06,
    "derived_model": -0.12,
    "absent": -0.06,
}


def _metadata_text(candidate: DatasetCandidate) -> str:
    fields = candidate.metadata_fields or {}
    parts = [
        candidate.title,
        candidate.description,
        fields.get("title", ""),
        fields.get("summary", ""),
    ]
    return _normalize_text(" ".join(part for part in parts if part))


def _exact_disease_terms(mapping: ConceptMapping) -> set[str]:
    terms = {
        _normalize_text(mapping.label),
        _normalize_text(mapping.query_term),
    }
    terms.update(_normalize_text(synonym) for synonym in mapping.synonyms)
    return {term for term in terms if term}


def _related_disease_terms(mapping: ConceptMapping) -> frozenset[str]:
    for key in (_normalize_text(mapping.label), _normalize_text(mapping.query_term)):
        related = DISEASE_RELATED_TERMS.get(key)
        if related:
            return related
    return frozenset()


def _text_mentions_any_term(text: str, terms: set[str] | frozenset[str]) -> bool:
    for term in terms:
        if term and term_in_text(term, text):
            return True
    return False


def disease_match_adjustment(
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    mapping: ConceptMapping | None,
) -> float:
    """Prefer exact requested disease evidence over related disease-family terms."""
    if mapping is None:
        return 0.0

    text = _metadata_text(candidate)
    exact_terms = _exact_disease_terms(mapping)
    related_terms = _related_disease_terms(mapping)
    has_exact = _text_mentions_any_term(text, exact_terms)
    has_related = _text_mentions_any_term(text, related_terms)

    if breakdown.disease.present:
        matched = {_normalize_text(term) for term in breakdown.disease.matched_terms}
        if matched & exact_terms:
            return 0.08
        if has_related and not (matched & exact_terms):
            return -0.12
        return 0.02

    if has_related and not has_exact:
        return -0.10
    return 0.0


def assay_match_adjustment(
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    mapping: ConceptMapping | None,
) -> float:
    """Deprecated path: assay adjustments are applied via domain.assay_ranking."""
    del candidate, breakdown, mapping
    return 0.0


def tissue_match_adjustment(
    breakdown: ScoreBreakdown,
    mapping: ConceptMapping | None,
) -> float:
    """Prefer direct tissue evidence over ambiguous or model-derived tissue context."""
    if mapping is None:
        return 0.0
    return TISSUE_EVIDENCE_ADJUSTMENTS.get(breakdown.tissue.evidence_type, 0.0)


def compute_facet_quality_adjustment(
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    concept_mappings: list[ConceptMapping],
) -> float:
    """Compute a bounded ranking adjustment from facet match quality signals."""
    mapping_by_slot = {mapping.slot: mapping for mapping in concept_mappings}
    adjustment = (
        disease_match_adjustment(candidate, breakdown, mapping_by_slot.get("disease"))
        + assay_match_adjustment(candidate, breakdown, mapping_by_slot.get("assay"))
        + tissue_match_adjustment(breakdown, mapping_by_slot.get("tissue"))
    )
    return round(adjustment, 3)


def match_tier(match_status: str) -> int:
    """Numeric priority tier derived from match_status (higher = ranks first)."""
    return MATCH_STATUS_ORDER.get(match_status, 0)


def match_tier_boost(match_status: str) -> float:
    """Tier component of display_rank_score (= match_tier × STATUS_TIER_WEIGHT)."""
    return match_tier(match_status) * STATUS_TIER_WEIGHT


def compute_display_rank_score(evidence_score: float, rank_tier: float) -> float:
    """Integrated ordering score: rank_tier × 10 + evidence_score."""
    return round(rank_tier * STATUS_TIER_WEIGHT + evidence_score, 3)


def explain_match_tier(match_status: str) -> str:
    """Explain how match_tier affects integrated rank relative to evidence_score."""
    tier = match_tier(match_status)
    explanations = {
        "full": (
            f"match_tier={tier} (full); sorted by display_rank_score among same-tier peers."
        ),
        "full_with_warnings": (
            f"match_tier={tier} (full_with_warnings); ranked below match_tier=4 full matches "
            "at equal evidence_score."
        ),
        "partial": (
            f"match_tier={tier} (partial); ranked above match_tier=1 ambiguous_or_mixed records "
            "even when their evidence_score is higher."
        ),
        "ambiguous_or_mixed": (
            f"match_tier={tier} (ambiguous_or_mixed); ranked below match_tier=2 partial records "
            "regardless of evidence_score (e.g. organoid tissue, mixed assays)."
        ),
        "model": (
            f"match_tier={tier} (model); ranked below match_tier=2 partial records regardless "
            "of evidence_score."
        ),
    }
    return explanations.get(
        match_status,
        f"match_tier={tier}; applied to display_rank_score = match_tier × 10 + evidence_score.",
    )


def ranking_sort_key(candidate: DatasetCandidate) -> tuple[float, str]:
    """Sort strongest matches first by display_rank_score, then accession."""
    display_score = (
        candidate.score_breakdown.display_rank_score
        if candidate.score_breakdown is not None
        else candidate.score
    )
    return (-display_score, candidate.accession)
