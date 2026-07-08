"""Extract structured slots from natural-language dataset queries."""

from __future__ import annotations

import re

from .dataset_search import InterpretedQuery
from .facet_abbreviation_resolution import resolve_abbreviated_facets
from .facet_phrase_resolution import resolve_phrase_facets
from .tissue_anatomy import build_tissue_patterns

DISEASE_PATTERNS = [
    (re.compile(r"ulcerative\s+colitis", re.I), "ulcerative colitis"),
    (re.compile(r"alzheimer(?:['\u2019]s)?\s+disease", re.I), "Alzheimer disease"),
    (re.compile(r"\bbreast\s+cancer\b", re.I), "breast cancer"),
    (re.compile(r"\basthma\b", re.I), "asthma"),
    (re.compile(r"\binflammatory\s+bowel\s+disease\b|\bibd\b", re.I), "inflammatory bowel disease"),
    (re.compile(r"\bCOVID(?:-19)?\b|\bSARS-CoV-2\b", re.I), "COVID-19"),
    (re.compile(r"esophagus\s+squamous\s+cell\s+carcinoma|\bESCC\b", re.I), "esophagus squamous cell carcinoma"),
]

TISSUE_PATTERNS = build_tissue_patterns()

ASSAY_PATTERNS = [
    (re.compile(r"\bimmune\s+repertoire(?:\s+sequencing)?\b", re.I), "immune repertoire sequencing"),
    (re.compile(r"\bBCR\s+repertoire\b", re.I), "BCR repertoire"),
    (re.compile(r"\bTCR\s+repertoire\b", re.I), "TCR repertoire"),
    (re.compile(r"\bAIRR[\s-]?seq(?:uencing)?\b", re.I), "AIRR-seq"),
    (re.compile(r"rna[\s-]?seq(?:uencing)?", re.I), "RNA-seq"),
    (re.compile(r"transcriptome\s+profiling", re.I), "RNA-seq"),
    (re.compile(r"\bproteomics\b", re.I), "proteomics"),
    (re.compile(r"\bmetabolomics\b", re.I), "metabolomics"),
    (re.compile(r"flow\s+cytometry", re.I), "Flow Cytometry"),
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

    interpreted = InterpretedQuery(
        disease=disease,
        tissue=tissue,
        assay=assay,
        organism=organism,
    )
    interpreted = resolve_abbreviated_facets(query, interpreted)
    return resolve_phrase_facets(query, interpreted)


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
