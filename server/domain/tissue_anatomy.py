"""Curated anatomy/tissue terms for query interpretation and UBERON grounding."""

from __future__ import annotations

import re
from typing import Any

# Canonical tissue facet definitions: regex → canonical query term → UBERON seed.
ANATOMY_TERMS: tuple[dict[str, Any], ...] = (
    {
        "canonical": "brain",
        "pattern": r"\bbrain(?:\s+tissue)?\b",
        "curie": "UBERON:0000955",
        "label": "brain",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000955",
        "synonyms": ["brain", "brain tissue"],
    },
    {
        "canonical": "cortex",
        "pattern": r"\b(?:cerebral\s+)?cortex\b",
        "curie": "UBERON:0000956",
        "label": "cerebral cortex",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000956",
        "synonyms": ["cortex", "cerebral cortex", "brain cortex"],
    },
    {
        "canonical": "hippocampus",
        "pattern": r"\bhippocamp(?:us|al)\b",
        "curie": "UBERON:0001954",
        "label": "hippocampus",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0001954",
        "synonyms": ["hippocampus", "hippocampal"],
    },
    {
        "canonical": "blood",
        "pattern": r"\b(?:whole\s+|peripheral\s+)?blood\b",
        "curie": "UBERON:0000178",
        "label": "blood",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000178",
        "synonyms": ["blood", "whole blood", "peripheral blood"],
    },
    {
        "canonical": "serum",
        "pattern": r"\b(?:blood\s+)?serum\b",
        "curie": "UBERON:0001977",
        "label": "serum",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0001977",
        "synonyms": ["serum", "blood serum"],
    },
    {
        "canonical": "liver",
        "pattern": r"\bliver\b|\bhepatic\b",
        "curie": "UBERON:0002107",
        "label": "liver",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0002107",
        "synonyms": ["liver", "hepatic"],
    },
    {
        "canonical": "lung",
        "pattern": r"\b(?:lung|pulmonary)\b",
        "curie": "UBERON:0002048",
        "label": "lung",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0002048",
        "synonyms": ["lung", "pulmonary"],
    },
    {
        "canonical": "kidney",
        "pattern": r"\b(?:kidney|renal)\b",
        "curie": "UBERON:0002113",
        "label": "kidney",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0002113",
        "synonyms": ["kidney", "renal"],
    },
    {
        "canonical": "colon",
        "pattern": r"\bcolon(?:ic)?\b|large\s+intestine|large\s+bowel",
        "curie": "UBERON:0001155",
        "label": "colon",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0001155",
        "synonyms": ["colon", "colonic", "large intestine", "large bowel"],
    },
    {
        "canonical": "breast",
        "pattern": r"\bbreast\s+tissue\b|\bbreast(?!\s+cancer\b)\b",
        "curie": "UBERON:0000310",
        "label": "breast",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000310",
        "synonyms": ["breast", "breast tissue", "mammary gland"],
    },
    {
        "canonical": "ileum",
        "pattern": r"\bileum\b|\bileal\b",
        "curie": "UBERON:0000167",
        "label": "ileum",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000167",
        "synonyms": ["ileum", "ileal"],
    },
    {
        "canonical": "heart",
        "pattern": r"\b(?:heart|cardiac)\b",
        "curie": "UBERON:0000948",
        "label": "heart",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000948",
        "synonyms": ["heart", "cardiac"],
    },
    {
        "canonical": "muscle",
        "pattern": r"\b(?:muscle|muscular)\b|skeletal\s+muscle",
        "curie": "UBERON:0001630",
        "label": "skeletal muscle tissue",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0001630",
        "synonyms": ["muscle", "skeletal muscle", "skeletal muscle tissue"],
    },
    {
        "canonical": "skin",
        "pattern": r"\b(?:skin|cutaneous)\b",
        "curie": "UBERON:0002097",
        "label": "skin of body",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0002097",
        "synonyms": ["skin", "cutaneous"],
    },
    {
        "canonical": "PBMC",
        "pattern": r"\bPBMCs?\b|peripheral\s+blood\s+mononuclear\s+cells?",
        "curie": "UBERON:0000178",
        "label": "PBMC",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000178",
        "synonyms": [
            "PBMC",
            "PBMCs",
            "peripheral blood mononuclear cell",
            "peripheral blood mononuclear cells",
        ],
    },
    {
        "canonical": "T cell",
        "pattern": r"\bT[\s-]?cells?\b",
        "curie": "CL:0000084",
        "label": "T cell",
        "ontology": "CL",
        "iri": "http://purl.obolibrary.org/obo/CL_0000084",
        "synonyms": ["T cell", "T cells", "T-cell", "T-cells"],
    },
    {
        "canonical": "B cell",
        "pattern": r"\bB[\s-]?cells?\b",
        "curie": "CL:0000236",
        "label": "B cell",
        "ontology": "CL",
        "iri": "http://purl.obolibrary.org/obo/CL_0000236",
        "synonyms": ["B cell", "B cells", "B-cell", "B-cells"],
    },
    {
        "canonical": "NK cell",
        "pattern": r"\bNK[\s-]?cells?\b",
        "curie": "CL:0000623",
        "label": "NK cell",
        "ontology": "CL",
        "iri": "http://purl.obolibrary.org/obo/CL_0000623",
        "synonyms": ["NK cell", "NK cells", "natural killer cell", "natural killer cells"],
    },
    {
        "canonical": "tumor",
        "pattern": r"\b(?:tumor|tumour|tumors|tumours|neoplasm|neoplasms)\b",
        "curie": "UBERON:0000428",
        "label": "neoplasm",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0000428",
        "synonyms": ["tumor", "tumour", "neoplasm", "neoplastic"],
    },
)


_BREAST_CANCER_CONTEXT = re.compile(r"\bbreast\s+cancer\b", re.I)
_BREAST_TISSUE_CONTEXT = re.compile(r"\bbreast\s+tissue\b", re.I)


def is_breast_tissue_query(query: str) -> bool:
    """Return True when breast should be interpreted as anatomy, not only as part of breast cancer."""
    if _BREAST_TISSUE_CONTEXT.search(query):
        return True
    if _BREAST_CANCER_CONTEXT.search(query):
        return False
    return bool(re.search(r"\bbreast\b", query, re.I))


def build_tissue_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Return regex patterns for anatomy terms, longest/specific patterns first."""
    ordered = sorted(
        ANATOMY_TERMS,
        key=lambda item: (-len(item["pattern"]), item["canonical"]),
    )
    return [
        (re.compile(entry["pattern"], re.I), entry["canonical"])
        for entry in ordered
    ]


def anatomy_seed_concepts() -> dict[str, dict[str, Any]]:
    """Build curated SEED_CONCEPTS entries for anatomy/tissue terms."""
    seeds: dict[str, dict[str, Any]] = {}
    for entry in ANATOMY_TERMS:
        seeds[entry["canonical"]] = {
            "slot": "tissue",
            "curie": entry["curie"],
            "label": entry["label"],
            "ontology": entry.get("ontology", "UBERON"),
            "iri": entry["iri"],
            "synonyms": list(entry["synonyms"]),
        }
    return seeds
