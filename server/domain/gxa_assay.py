"""Expression Atlas experiment-type to assay normalization."""

from __future__ import annotations

import re

from .dataset_search import ConceptMapping
from .synonym_classification import _normalize_text

GXA_EXPERIMENT_TYPE_FIELD = "gxa_experiment_type"
GXA_OBSERVED_ASSAY_FIELD = "gxa_observed_assay"


def infer_observed_assay_from_gxa_experiment_type(experiment_type: str) -> str:
    """Map a GXA experiment type string to a normalized observed assay label."""
    normalized = _normalize_text(experiment_type.replace("_", " "))
    if not normalized:
        return "unknown"

    compact = normalized.replace(" ", "")
    if "proteom" in normalized or "lcms" in compact or "lcmss" in compact:
        return "proteomics"
    if "rnaseq" in compact or "rnasequ" in compact:
        return "RNA-seq"
    if "microarray" in normalized or re.search(r"\barray\b", normalized):
        return "microarray"
    if "atacseq" in compact or "atac seq" in normalized:
        return "ATAC-seq"
    if "chipseq" in compact or "chip seq" in normalized:
        return "ChIP-seq"
    if "methylation" in normalized:
        return "methylation"
    return "unknown"


def gxa_supports_requested_assay(experiment_type: str, requested_label: str) -> bool:
    """Return True when a GXA experiment type supports the requested assay facet."""
    observed = infer_observed_assay_from_gxa_experiment_type(experiment_type)
    if observed == "unknown":
        return False
    return _normalize_text(observed) == _normalize_text(requested_label)


def build_gxa_assay_warning(
    fields: dict[str, str],
    assay_mapping: ConceptMapping | None,
) -> str | None:
    """Build a user-facing warning when a GXA experiment type mismatches the requested assay."""
    if assay_mapping is None:
        return None

    experiment_type = fields.get(GXA_EXPERIMENT_TYPE_FIELD, "").strip()
    if not experiment_type:
        return None

    observed = fields.get(GXA_OBSERVED_ASSAY_FIELD) or infer_observed_assay_from_gxa_experiment_type(
        experiment_type
    )
    requested = assay_mapping.label
    if gxa_supports_requested_assay(experiment_type, requested):
        return None

    if observed == "unknown":
        return (
            f"Expression Atlas experiment type `{experiment_type}` does not indicate "
            f"requested {requested}; assay evidence treated as missing."
        )
    return (
        f"Assay mismatch: requested {requested}, but Expression Atlas experiment type "
        f"indicates {observed} (`{experiment_type}`)."
    )


def annotate_gxa_metadata_fields(
    metadata_fields: dict[str, str],
    *,
    experiment_type: str,
    assay_type: str = "",
) -> dict[str, str]:
    """Attach GXA structured assay metadata used by evidence extraction."""
    enriched = dict(metadata_fields)
    resolved_type = experiment_type.strip() or assay_type.strip()
    if not resolved_type:
        return enriched

    enriched[GXA_EXPERIMENT_TYPE_FIELD] = resolved_type
    observed = infer_observed_assay_from_gxa_experiment_type(resolved_type)
    if observed != "unknown":
        enriched[GXA_OBSERVED_ASSAY_FIELD] = observed
    return enriched
