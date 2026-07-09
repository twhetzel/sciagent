"""AIRR / immune repertoire assay normalization for evidence extraction."""

from __future__ import annotations

import re

from .dataset_search import ConceptMapping
from .repository_vocab.vdjserver_vocab import resolve_vdjserver_facet_value
from .synonym_classification import _normalize_text

AIRR_OBSERVED_ASSAY_FIELD = "airr_observed_assay"

_LOCUS_TO_ASSAY: dict[str, str] = {
    "IGH": "B cell receptor repertoire sequencing",
    "IGK": "B cell receptor repertoire sequencing",
    "IGL": "B cell receptor repertoire sequencing",
    "TRA": "T cell receptor repertoire sequencing",
    "TRB": "T cell receptor repertoire sequencing",
    "TRD": "T cell receptor repertoire sequencing",
    "TRG": "T cell receptor repertoire sequencing",
}

_KEYWORD_TO_ASSAY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bcontains?_ig\b", re.I), "B cell receptor repertoire sequencing"),
    (re.compile(r"\bcontains?_tr\b", re.I), "T cell receptor repertoire sequencing"),
)


def _requested_assay_aliases(requested_label: str) -> set[str]:
    aliases = {
        _normalize_text(requested_label),
        _normalize_text(requested_label.replace("BCR", "B cell receptor")),
        _normalize_text(requested_label.replace("TCR", "T cell receptor")),
    }
    resolved = resolve_vdjserver_facet_value("assay", requested_label)
    if resolved:
        aliases.add(_normalize_text(resolved))
    aliases.discard("")
    return aliases


def infer_observed_assay_from_airr_metadata(*, assay_method: str = "") -> str:
    """Map AIRR locus / keyword metadata to a normalized repertoire assay label."""
    combined = assay_method.strip()
    if not combined:
        return "unknown"

    normalized = _normalize_text(combined)
    for pattern, label in _KEYWORD_TO_ASSAY:
        if pattern.search(normalized):
            return label

    for fragment in re.split(r"[,;]", combined):
        token = fragment.strip().upper()
        if token in _LOCUS_TO_ASSAY:
            return _LOCUS_TO_ASSAY[token]

    if "repertoire" in normalized or "airr" in normalized:
        return "immune repertoire deep sequencing"
    return "unknown"


def airr_supports_requested_assay(
    *,
    assay_method: str,
    requested_label: str,
) -> bool:
    """Return True when AIRR structured assay metadata supports the requested assay facet."""
    observed = infer_observed_assay_from_airr_metadata(assay_method=assay_method)
    if observed == "unknown":
        return False

    requested_aliases = _requested_assay_aliases(requested_label)
    observed_norm = _normalize_text(observed)
    if observed_norm in requested_aliases:
        return True

    for alias in requested_aliases:
        if alias in observed_norm or observed_norm in alias:
            return True
        if "bcr" in alias and "b cell receptor" in observed_norm:
            return True
        if "tcr" in alias and "t cell receptor" in observed_norm:
            return True
        if alias in {"bcr repertoire", "bcr"} and "b cell receptor repertoire" in observed_norm:
            return True
        if alias in {"tcr repertoire", "tcr"} and "t cell receptor repertoire" in observed_norm:
            return True
    return False


def build_airr_assay_warning(
    fields: dict[str, str],
    assay_mapping: ConceptMapping | None,
) -> str | None:
    """Build a warning when AIRR assay metadata mismatches the requested repertoire assay."""
    if assay_mapping is None:
        return None

    assay_method = fields.get("assay_method", "").strip()
    if not assay_method:
        return None

    observed = fields.get(AIRR_OBSERVED_ASSAY_FIELD) or infer_observed_assay_from_airr_metadata(
        assay_method=assay_method
    )
    requested = assay_mapping.label
    if airr_supports_requested_assay(assay_method=assay_method, requested_label=requested):
        return None

    if observed == "unknown":
        return (
            f"AIRR metadata `{assay_method}` does not indicate requested {requested}; "
            "assay evidence treated as missing."
        )
    return (
        f"Assay mismatch: requested {requested}, but AIRR metadata indicates "
        f"{observed} (`{assay_method}`)."
    )


def annotate_airr_metadata_fields(
    metadata_fields: dict[str, str],
    *,
    assay_method: str = "",
) -> dict[str, str]:
    """Attach AIRR structured assay metadata used by evidence extraction."""
    enriched = dict(metadata_fields)
    resolved_method = assay_method.strip()
    if resolved_method:
        enriched.setdefault("assay_method", resolved_method)

    observed = infer_observed_assay_from_airr_metadata(assay_method=resolved_method)
    if observed != "unknown":
        enriched[AIRR_OBSERVED_ASSAY_FIELD] = observed
    return enriched
