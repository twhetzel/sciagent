"""OmicsDI REST API facet term normalization."""

from __future__ import annotations

import re

STATIC_FACET_OVERRIDES: dict[tuple[str, str], str] = {
    ("disease", "asthma"): "asthma",
    ("disease", "breast cancer"): "Breast cancer",
    ("disease", "ulcerative colitis"): "ulcerative colitis",
    ("disease", "uc"): "ulcerative colitis",
    ("disease", "crohn's disease"): "Crohn's disease",
    ("disease", "crohn disease"): "Crohn's disease",
    ("disease", "alzheimer's disease"): "Alzheimer's disease",
    ("disease", "alzheimer disease"): "Alzheimer's disease",
    ("disease", "alzheimer"): "Alzheimer's disease",
    ("disease", "tuberculosis"): "tuberculosis",
    ("disease", "tb"): "tuberculosis",
    ("tissue", "colon"): "Colon",
    ("tissue", "brain"): "Brain",
    ("tissue", "breast"): "Breast",
    ("tissue", "lung"): "Lung",
    ("tissue", "ileum"): "Ileum",
    ("tissue", "liver"): "Liver",
    ("tissue", "kidney"): "Kidney",
    ("assay", "rna-seq"): "Transcriptomics",
    ("assay", "rnaseq"): "Transcriptomics",
    ("assay", "transcriptomics"): "Transcriptomics",
    ("assay", "proteomics"): "Proteomics",
    ("assay", "metabolomics"): "Metabolomics",
    ("assay", "genomics"): "Genomics",
    ("assay", "mass spectrometry"): "Mass Spectrometry",
    ("organism", "human"): "9606",
    ("organism", "homo sapiens"): "9606",
    ("organism", "mouse"): "10090",
    ("organism", "mus musculus"): "10090",
}

OMICS_TYPE_VALUES = frozenset({"Proteomics", "Metabolomics", "Genomics", "Transcriptomics"})


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def resolve_omicsdi_facet_value(slot: str, term: str | None) -> str | None:
    """Map a grounded label to an OmicsDI query facet value."""
    if not term or not str(term).strip():
        return None
    normalized = _normalize_key(term)
    override = STATIC_FACET_OVERRIDES.get((slot, normalized))
    if override:
        return override
    if slot == "disease":
        return term.strip()
    if slot == "tissue":
        stripped = term.strip()
        return stripped[:1].upper() + stripped[1:] if stripped else None
    return term.strip()


def omicsdi_assay_filter_clauses(assay_value: str | None) -> list[str]:
    """Return OmicsDI query clauses for an assay / omics-type facet."""
    if not assay_value:
        return []
    if assay_value in OMICS_TYPE_VALUES:
        return [f'omics_type:"{assay_value}"']
    if assay_value == "Mass Spectrometry":
        return [f'technology_type:"{assay_value}"']
    escaped = assay_value.replace('"', '\\"')
    return [f'"{escaped}"']


def map_term_to_omicsdi_facet(slot: str, term: str | None) -> str | None:
    """Public alias for repository vocab tests and adapters."""
    return resolve_omicsdi_facet_value(slot, term)
