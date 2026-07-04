"""Assay-aware ranking signals for integrated GEO + Expression Atlas results."""

from __future__ import annotations

from .dataset_search import ConceptMapping, DatasetCandidate, ScoreBreakdown
from .evidence_extraction import MIXED_ASSAY_LABEL
from .synonym_classification import _normalize_text

RNA_SEQ_REQUEST_LABEL = "rna-seq"

NON_RNA_SEQ_OBSERVED_ASSAYS = frozenset(
    {
        "microarray",
        "proteomics",
        "atac-seq",
        "chip-seq",
        "methylation",
        "occupancy",
    }
)

ASSAY_MISMATCH_PENALTIES: dict[str, float] = {
    "proteomics": -0.32,
    "microarray": -0.26,
    "atac-seq": -0.20,
    "chip-seq": -0.20,
    "methylation": -0.20,
    "occupancy": -0.16,
}

PARTIAL_ASSAY_MISMATCH_EXTRA = -0.20

RNA_SEQ_SUPPORTED_BONUS = 0.08
RNA_SEQ_OBSERVED_BONUS = 0.05

# Partial sub-tiers for assay-specific queries (rank_tier × 10 + evidence_score).
PARTIAL_ASSAY_SUPPORTED = "partial_assay_supported"
PARTIAL_ASSAY_UNKNOWN = "partial_assay_unknown"
PARTIAL_ASSAY_MISMATCH = "partial_assay_mismatch"

RANK_TIER_BY_STATUS: dict[str, float] = {
    "full": 4.0,
    "full_with_warnings": 3.0,
    "ambiguous_or_mixed": 1.0,
    "model": 1.0,
}

RANK_TIER_PARTIAL_ASSAY: dict[str, float] = {
    PARTIAL_ASSAY_SUPPORTED: 2.8,
    PARTIAL_ASSAY_UNKNOWN: 2.5,
    PARTIAL_ASSAY_MISMATCH: 2.2,
}

DEFAULT_PARTIAL_RANK_TIER = 2.0


def is_rna_seq_request(assay_mapping: ConceptMapping | None) -> bool:
    if assay_mapping is None:
        return False
    return _normalize_text(assay_mapping.label) == RNA_SEQ_REQUEST_LABEL


def detect_assay_mismatch(
    assay_mapping: ConceptMapping | None,
    observed_assay: str | None,
    *,
    accession: str = "",
) -> tuple[bool, str]:
    """Return whether requested assay differs from observed metadata for ranking/export."""
    if not is_rna_seq_request(assay_mapping):
        return False, ""

    if accession.upper().startswith("E-PROT-"):
        return True, (
            "Requested RNA-seq, but accession indicates Expression Atlas proteomics (E-PROT)."
        )

    observed_norm = _normalize_text(observed_assay or "unknown")
    if observed_norm in {RNA_SEQ_REQUEST_LABEL, "unknown"}:
        return False, ""

    if observed_norm == _normalize_text(MIXED_ASSAY_LABEL):
        return True, "Requested RNA-seq, but metadata indicates a mixed or multi-assay study."

    if observed_norm in NON_RNA_SEQ_OBSERVED_ASSAYS:
        label = observed_assay or observed_norm
        return True, f"Requested RNA-seq, observed {label} in returned metadata."

    return False, ""


def compute_assay_rank_adjustment(
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    assay_mapping: ConceptMapping | None,
    *,
    match_status: str | None = None,
) -> tuple[float, bool, str]:
    """
    Assay-specific evidence_score adjustment for RNA-seq queries.

    Non-RNA-seq observed assays receive a modest penalty; RNA-seq evidence receives a bonus.
    Partial matches with assay mismatch receive an additional penalty so RNA-seq partials
    rank above proteomics/microarray partials at similar facet coverage.
    """
    mismatch, note = detect_assay_mismatch(
        assay_mapping,
        candidate.observed_assay,
        accession=candidate.accession,
    )
    if not is_rna_seq_request(assay_mapping):
        return 0.0, mismatch, note

    observed_norm = _normalize_text(candidate.observed_assay or "unknown")
    if mismatch:
        penalty = ASSAY_MISMATCH_PENALTIES.get(observed_norm, -0.18)
        if candidate.accession.upper().startswith("E-PROT-"):
            penalty = ASSAY_MISMATCH_PENALTIES["proteomics"]
        effective_status = match_status or candidate.match_status
        if effective_status == "partial":
            penalty += PARTIAL_ASSAY_MISMATCH_EXTRA
        return round(penalty, 3), True, note

    if breakdown.assay.present and observed_norm == RNA_SEQ_REQUEST_LABEL:
        return RNA_SEQ_SUPPORTED_BONUS, False, ""
    if observed_norm == RNA_SEQ_REQUEST_LABEL:
        return RNA_SEQ_OBSERVED_BONUS, False, ""
    return 0.0, False, ""


def rna_seq_assay_supported(
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    assay_mapping: ConceptMapping | None,
) -> bool:
    """True when returned metadata supports the requested RNA-seq assay."""
    if not is_rna_seq_request(assay_mapping):
        return False
    observed_norm = _normalize_text(candidate.observed_assay or "unknown")
    if observed_norm == RNA_SEQ_REQUEST_LABEL:
        return True
    if breakdown.assay.present:
        return True
    return any(mapping.slot == "assay" for mapping in candidate.matched_concepts)


def classify_partial_assay_subtype(
    match_status: str,
    assay_mapping: ConceptMapping | None,
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    assay_mismatch: bool,
) -> str | None:
    """Classify partial matches by assay support for assay-specific queries."""
    if match_status != "partial" or not is_rna_seq_request(assay_mapping):
        return None
    if assay_mismatch:
        return PARTIAL_ASSAY_MISMATCH
    if rna_seq_assay_supported(candidate, breakdown, assay_mapping):
        return PARTIAL_ASSAY_SUPPORTED
    return PARTIAL_ASSAY_UNKNOWN


def compute_rank_tier(
    match_status: str,
    assay_mapping: ConceptMapping | None,
    candidate: DatasetCandidate,
    breakdown: ScoreBreakdown,
    assay_mismatch: bool,
) -> tuple[float, str | None]:
    """
    Compute integrated rank tier, including partial assay sub-tiers for RNA-seq queries.

    Order (high to low): full > full_with_warnings > partial (assay supported) >
    partial (assay unknown) > partial (assay mismatch) > ambiguous_or_mixed/model.
    """
    if match_status in RANK_TIER_BY_STATUS:
        return RANK_TIER_BY_STATUS[match_status], None

    if match_status == "partial":
        subtype = classify_partial_assay_subtype(
            match_status,
            assay_mapping,
            candidate,
            breakdown,
            assay_mismatch,
        )
        if subtype is not None:
            return RANK_TIER_PARTIAL_ASSAY[subtype], subtype
        return DEFAULT_PARTIAL_RANK_TIER, None

    return 0.0, None


def explain_rank_tier(
    match_status: str,
    rank_tier: float,
    partial_assay_subtype: str | None,
) -> str:
    """Explain rank_tier and partial assay subtype used for display_rank_score."""
    if partial_assay_subtype == PARTIAL_ASSAY_SUPPORTED:
        return (
            f"rank_tier={rank_tier} (partial, assay supported); ranks above assay-unknown "
            f"(tier {RANK_TIER_PARTIAL_ASSAY[PARTIAL_ASSAY_UNKNOWN]}) and assay-mismatch "
            f"(tier {RANK_TIER_PARTIAL_ASSAY[PARTIAL_ASSAY_MISMATCH]}) partial results."
        )
    if partial_assay_subtype == PARTIAL_ASSAY_UNKNOWN:
        return (
            f"rank_tier={rank_tier} (partial, assay unknown); ranks above assay-mismatch "
            "partials but below assay-supported partials."
        )
    if partial_assay_subtype == PARTIAL_ASSAY_MISMATCH:
        return (
            f"rank_tier={rank_tier} (partial, assay mismatch); kept as related partial result "
            "but ranked below RNA-seq-supported partials."
        )
    if match_status == "partial":
        return (
            f"rank_tier={rank_tier} (partial); sorted by display_rank_score among partial peers."
        )
    return (
        f"rank_tier={rank_tier} ({match_status}); "
        "display_rank_score = rank_tier × 10 + evidence_score."
    )


def rna_seq_supported(candidate: DatasetCandidate) -> bool:
    """True when returned metadata supports RNA-seq for an RNA-seq query context."""
    observed_norm = _normalize_text(candidate.observed_assay or "unknown")
    if observed_norm == RNA_SEQ_REQUEST_LABEL:
        return True
    if candidate.score_breakdown is not None and candidate.score_breakdown.assay.present:
        return True
    return any(mapping.slot == "assay" for mapping in candidate.matched_concepts)


def assay_mismatch_partial(candidate: DatasetCandidate) -> bool:
    """True when a partial result has an assay mismatch for an RNA-seq query."""
    if candidate.match_status != "partial":
        return False
    if candidate.assay_mismatch:
        return True
    breakdown = candidate.score_breakdown
    return breakdown is not None and breakdown.partial_assay_subtype == PARTIAL_ASSAY_MISMATCH


def validate_rna_seq_assay_ranking(
    concept_mappings: list[ConceptMapping],
    ranked: list[DatasetCandidate],
    *,
    top_n: int,
) -> list[str]:
    """
    Return violation messages when assay-mismatch partials rank above RNA-seq-supported partials.

    Used by the golden-query harness for RNA-seq queries.
    """
    assay_mapping = next((mapping for mapping in concept_mappings if mapping.slot == "assay"), None)
    if not is_rna_seq_request(assay_mapping):
        return []

    top = ranked[:top_n]
    rank_by_accession = {candidate.accession: index for index, candidate in enumerate(top, start=1)}

    supported_partials = [
        candidate
        for candidate in top
        if candidate.match_status == "partial" and rna_seq_supported(candidate)
    ]
    mismatch_partials = [candidate for candidate in top if assay_mismatch_partial(candidate)]

    if not supported_partials or not mismatch_partials:
        return []

    violations: list[str] = []
    for mismatch in mismatch_partials:
        mismatch_rank = rank_by_accession[mismatch.accession]
        subtype = (
            mismatch.score_breakdown.partial_assay_subtype
            if mismatch.score_breakdown is not None
            else PARTIAL_ASSAY_MISMATCH
        )
        for supported in supported_partials:
            supported_rank = rank_by_accession[supported.accession]
            if mismatch_rank < supported_rank:
                violations.append(
                    f"{mismatch.accession} (rank {mismatch_rank}, {subtype}) ranked above "
                    f"{supported.accession} (rank {supported_rank}, RNA-seq supported partial)"
                )
    return violations
