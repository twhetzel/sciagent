"""Vivli / NIAID Discovery API facet term normalization."""

from __future__ import annotations

import re

STATIC_FACET_OVERRIDES: dict[tuple[str, str], str] = {
    ("disease", "uc"): "ulcerative colitis",
    ("disease", "ibd"): "inflammatory bowel disease",
    ("disease", "hiv"): "HIV Infections",
    ("disease", "aids"): "Acquired Immunodeficiency Syndrome",
    ("disease", "covid"): "COVID-19",
    ("disease", "covid-19"): "COVID-19",
    ("disease", "sars-cov-2"): "COVID-19",
    ("tissue", "pbmc"): "Peripheral Blood Mononuclear Cell",
    ("tissue", "pbmcs"): "Peripheral Blood Mononuclear Cell",
    ("tissue", "blood"): "Whole Blood",
    ("tissue", "plasma"): "Plasma",
    ("tissue", "serum"): "Serum",
    ("assay", "flow cytometry"): "Flow Cytometry",
    ("assay", "rna-seq"): "RNA-seq",
    ("assay", "rnaseq"): "RNA-seq",
}


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def resolve_vivli_facet_value(slot: str, term: str | None) -> str | None:
    """Map a grounded label to a Vivli / NIAID Discovery API facet value."""
    if not term or not str(term).strip():
        return None
    normalized = _normalize_key(term)
    override = STATIC_FACET_OVERRIDES.get((slot, normalized))
    if override:
        return override
    return term.strip()


def map_term_to_vivli_facet(slot: str, term: str | None) -> str | None:
    """Public alias for repository vocab tests and adapters."""
    return resolve_vivli_facet_value(slot, term)
