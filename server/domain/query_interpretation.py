"""Extract structured slots from natural-language dataset queries."""

from __future__ import annotations

import re

from .dataset_search import InterpretedQuery

DISEASE_PATTERNS = [
    (re.compile(r"ulcerative\s+colitis", re.I), "ulcerative colitis"),
]

TISSUE_PATTERNS = [
    (re.compile(r"\bcolon(?:ic)?\b", re.I), "colon"),
    (re.compile(r"large\s+intestine", re.I), "colon"),
]

ASSAY_PATTERNS = [
    (re.compile(r"rna[\s-]?seq(?:uencing)?", re.I), "RNA-seq"),
    (re.compile(r"transcriptome\s+profiling", re.I), "RNA-seq"),
]

ORGANISM_PATTERNS = [
    (re.compile(r"\bhuman(s)?\b", re.I), "human"),
    (re.compile(r"homo\s+sapiens", re.I), "human"),
]


def _first_match(patterns: list, text: str) -> str | None:
    for pattern, value in patterns:
        if pattern.search(text):
            return value
    return None


def interpret_dataset_query(query: str) -> InterpretedQuery:
    """Extract disease, tissue, assay, and organism from a dataset query."""
    disease = _first_match(DISEASE_PATTERNS, query)
    tissue = _first_match(TISSUE_PATTERNS, query)
    assay = _first_match(ASSAY_PATTERNS, query)
    organism = _first_match(ORGANISM_PATTERNS, query)

    # Clinical tissue queries without an explicit organism default to human.
    if organism is None and (disease or tissue):
        organism = "human"

    return InterpretedQuery(
        disease=disease,
        tissue=tissue,
        assay=assay,
        organism=organism,
    )


def is_dataset_discovery_query(query: str) -> bool:
    """Return True when the query targets public omics dataset discovery."""
    query_lower = query.lower()
    dataset_keywords = [
        "dataset",
        "datasets",
        "data set",
        "geo",
        "gse",
        "expression data",
        "transcriptome",
        "microarray",
        "rna-seq",
        "rna seq",
        "rnaseq",
        "public data",
    ]
    return any(keyword in query_lower for keyword in dataset_keywords)
