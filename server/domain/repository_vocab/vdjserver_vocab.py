"""VDJServer AIRR Data Commons API facet term normalization."""

from __future__ import annotations

import re

STATIC_FACET_OVERRIDES: dict[tuple[str, str], str] = {
    ("disease", "covid"): "COVID-19",
    ("disease", "covid-19"): "COVID-19",
    ("disease", "sars-cov-2"): "COVID-19",
    ("disease", "hiv"): "human immunodeficiency virus infectious disease",
    ("disease", "aids"): "acquired immunodeficiency syndrome",
    ("tissue", "pbmc"): "blood",
    ("tissue", "pbmcs"): "blood",
    ("tissue", "peripheral blood"): "blood",
    ("tissue", "whole blood"): "blood",
    ("organism", "human"): "NCBITAXON:9606",
    ("organism", "homo sapiens"): "NCBITAXON:9606",
    ("organism", "mouse"): "NCBITAXON:10090",
    ("organism", "mus musculus"): "NCBITAXON:10090",
    ("assay", "bcr"): "IGH",
    ("assay", "bcr repertoire"): "IGH",
    ("assay", "b cell receptor repertoire sequencing"): "IGH",
    ("assay", "b cell receptor repertoire"): "IGH",
    ("assay", "b cell receptor"): "IGH",
    ("assay", "tcr"): "TRB",
    ("assay", "tcr repertoire"): "TRB",
    ("assay", "t cell receptor repertoire sequencing"): "TRB",
    ("assay", "t cell receptor"): "TRB",
    ("assay", "t cell receptor repertoire"): "TRB",
    ("assay", "immune repertoire"): "AIRR-seq",
    ("assay", "immune repertoire sequencing"): "AIRR-seq",
    ("assay", "airr-seq"): "AIRR-seq",
    ("assay", "repertoire sequencing"): "AIRR-seq",
}


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def resolve_vdjserver_facet_value(slot: str, term: str | None) -> str | None:
    """Map a grounded label to a VDJServer AIRR API facet value."""
    if not term or not str(term).strip():
        return None
    normalized = _normalize_key(term)
    override = STATIC_FACET_OVERRIDES.get((slot, normalized))
    if override:
        return override
    if slot == "tissue":
        return normalized
    return term.strip()


def vdjserver_assay_filter(value: str | None) -> dict[str, str] | None:
    """Return an AIRR filter clause for an assay / receptor locus, if mappable."""
    if not value:
        return None
    resolved = resolve_vdjserver_facet_value("assay", value) or value.strip()
    locus_values = {"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"}
    if resolved.upper() in locus_values:
        return {
            "op": "=",
            "content": {
                "field": "sample.pcr_target.pcr_target_locus",
                "value": resolved.upper(),
            },
        }
    return {
        "op": "contains",
        "content": {
            "field": "study.study_title",
            "value": resolved,
        },
    }


def map_term_to_vdjserver_facet(slot: str, term: str | None) -> str | None:
    """Public alias for repository vocab tests and adapters."""
    return resolve_vdjserver_facet_value(slot, term)
