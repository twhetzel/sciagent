"""OmicsDI omics_type / technology_type to assay normalization."""

from __future__ import annotations

import re

from .dataset_search import ConceptMapping
from .synonym_classification import _normalize_text

OMICSDI_OMICS_TYPE_FIELD = "omicsdi_omics_type"
OMICSDI_OBSERVED_ASSAY_FIELD = "omicsdi_observed_assay"


def infer_observed_assay_from_omicsdi_metadata(
    *,
    omics_type: str = "",
    assay_method: str = "",
) -> str:
    """Map OmicsDI omics_type and technology metadata to a normalized observed assay label."""
    combined = _normalize_text(f"{omics_type} {assay_method}".replace("_", " "))
    if not combined:
        return "unknown"

    if "transcriptomic" in combined:
        return "RNA-seq"
    if (
        "proteomic" in combined
        or "mass spectromet" in combined
        or "shotgun proteomic" in combined
        or re.search(r"\blc[\s-]?ms", combined)
    ):
        return "proteomics"
    if "metabolomic" in combined:
        return "metabolomics"
    if "genomic" in combined:
        return "genomics"
    return "unknown"


def omicsdi_supports_requested_assay(
    *,
    omics_type: str,
    assay_method: str,
    requested_label: str,
) -> bool:
    """Return True when OmicsDI structured assay metadata supports the requested assay facet."""
    observed = infer_observed_assay_from_omicsdi_metadata(
        omics_type=omics_type,
        assay_method=assay_method,
    )
    if observed == "unknown":
        return False
    return _normalize_text(observed) == _normalize_text(requested_label)


def build_omicsdi_assay_warning(
    fields: dict[str, str],
    assay_mapping: ConceptMapping | None,
) -> str | None:
    """Build a user-facing warning when OmicsDI assay metadata mismatches the requested assay."""
    if assay_mapping is None:
        return None

    omics_type = fields.get(OMICSDI_OMICS_TYPE_FIELD, "").strip()
    assay_method = fields.get("assay_method", "").strip()
    if not omics_type and not assay_method:
        return None

    observed = fields.get(OMICSDI_OBSERVED_ASSAY_FIELD) or infer_observed_assay_from_omicsdi_metadata(
        omics_type=omics_type,
        assay_method=assay_method,
    )
    requested = assay_mapping.label
    if omicsdi_supports_requested_assay(
        omics_type=omics_type,
        assay_method=assay_method,
        requested_label=requested,
    ):
        return None

    if observed == "unknown":
        label = omics_type or assay_method
        return (
            f"OmicsDI metadata `{label}` does not indicate requested {requested}; "
            "assay evidence treated as missing."
        )
    return (
        f"Assay mismatch: requested {requested}, but OmicsDI metadata indicates "
        f"{observed} (`{omics_type or assay_method}`)."
    )


def annotate_omicsdi_metadata_fields(
    metadata_fields: dict[str, str],
    *,
    omics_type: str,
    assay_method: str = "",
) -> dict[str, str]:
    """Attach OmicsDI structured assay metadata used by evidence extraction."""
    enriched = dict(metadata_fields)
    resolved_omics = omics_type.strip()
    resolved_method = assay_method.strip()
    if resolved_omics:
        enriched[OMICSDI_OMICS_TYPE_FIELD] = resolved_omics
    if resolved_method:
        enriched.setdefault("assay_method", resolved_method)

    observed = infer_observed_assay_from_omicsdi_metadata(
        omics_type=resolved_omics,
        assay_method=resolved_method,
    )
    if observed != "unknown":
        enriched[OMICSDI_OBSERVED_ASSAY_FIELD] = observed
    return enriched
