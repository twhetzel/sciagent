"""Extract observed metadata and evidence snippets from dataset records."""

from __future__ import annotations

import re
from typing import Iterable

from .dataset_search import ConceptMapping, EvidenceSnippet
from .ontology_grounding import search_terms_for_mapping

# Order matters: check specific / conflicting assays before RNA-seq.
ASSAY_DETECTORS: list[tuple[str, list[str]]] = [
    ("ATAC-seq", [r"\batac[\s-]?seq\b", r"transposase-accessible"]),
    ("ChIP-seq", [r"\bchip[\s-]?seq\b", r"chromatin immunoprecipitation"]),
    ("methylation", [r"\bmethylation\b", r"\bbisulfite\b", r"\b450k\b", r"\be methylation\b"]),
    ("microarray", [r"\bmicroarray\b", r"\baffymetrix\b", r"\bagilent\b.*\barray\b"]),
    (
        "RNA-seq",
        [
            r"\brna[\s-]?seq\b",
            r"\brna sequencing\b",
            r"\brnaseq\b",
            r"\bmrna[\s-]?seq\b",
            r"\btranscriptome profiling\b",
            r"\bexpression profiling by high throughput sequencing\b",
        ],
    ),
]

GDS_TYPE_ASSAY_HINTS: list[tuple[str, str]] = [
    ("expression profiling by high throughput sequencing", "RNA-seq"),
    ("non-coding rna profiling by high throughput sequencing", "RNA-seq"),
    ("genome binding/occupancy profiling by high throughput sequencing", "ATAC-seq"),
    ("methylation profiling by high throughput sequencing", "methylation"),
    ("array", "microarray"),
]

CONFLICTING_ASSAYS_FOR_RNA_SEQ = {"ATAC-seq", "ChIP-seq", "methylation", "microarray"}

SLOT_FIELD_PRIORITY = (
    "title",
    "summary",
    "gdstype",
    "platformtitle",
    "platformtaxa",
    "ptechtype",
    "taxon",
    "sample_titles",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _term_in_text(term: str, text: str) -> bool:
    normalized_term = _normalize_text(term)
    normalized_text = _normalize_text(text)
    if not normalized_term or not normalized_text:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"\b{re.escape(normalized_term)}\b", normalized_text) is not None


def _first_pattern_match(text: str, patterns: Iterable[str]) -> bool:
    normalized = _normalize_text(text)
    return any(re.search(pattern, normalized, re.I) for pattern in patterns)


def collect_metadata_fields(
    *,
    title: str = "",
    description: str = "",
    taxon: str | None = None,
    gdstype: str | None = None,
    platformtitle: str | None = None,
    platformtaxa: str | None = None,
    ptechtype: str | None = None,
    sample_titles: list[str] | None = None,
) -> dict[str, str]:
    """Normalize repository metadata into searchable evidence fields."""
    fields: dict[str, str] = {
        "title": title.strip(),
        "summary": description.strip(),
    }
    if gdstype:
        fields["gdstype"] = str(gdstype).strip()
    if platformtitle:
        fields["platformtitle"] = str(platformtitle).strip()
    if platformtaxa:
        fields["platformtaxa"] = str(platformtaxa).strip()
    if ptechtype:
        fields["ptechtype"] = str(ptechtype).strip()
    if taxon:
        fields["taxon"] = str(taxon).strip()
    if sample_titles:
        joined = "; ".join(title.strip() for title in sample_titles if title.strip())
        if joined:
            fields["sample_titles"] = joined
    return fields


def _detect_from_title_tags(title: str) -> str | None:
    tag_patterns = [
        ("ATAC-seq", r"\[atac[\s-]?seq\]"),
        ("RNA-seq", r"\[rna[\s-]?seq\]"),
        ("ChIP-seq", r"\[chip[\s-]?seq\]"),
    ]
    for label, pattern in tag_patterns:
        if re.search(pattern, title, re.I):
            return label
    return None


def detect_observed_assay(fields: dict[str, str]) -> str:
    """Infer assay type from record metadata only."""
    title = fields.get("title", "")
    tagged = _detect_from_title_tags(title)
    if tagged:
        return tagged

    gdstype = _normalize_text(fields.get("gdstype", ""))
    for hint, assay in GDS_TYPE_ASSAY_HINTS:
        if hint in gdstype and assay != "ATAC-seq":
            return assay

    title_text = " ".join(
        part for part in (fields.get("title", ""), fields.get("platformtitle", ""), fields.get("ptechtype", ""))
        if part
    )
    for label, patterns in ASSAY_DETECTORS:
        if _first_pattern_match(title_text, patterns):
            return label

    if "genome binding/occupancy profiling by high throughput sequencing" in gdstype:
        occupancy_text = " ".join(fields.get(key, "") for key in ("title", "summary", "gdstype"))
        if _first_pattern_match(occupancy_text, ASSAY_DETECTORS[0][1]):
            return "ATAC-seq"
        if _first_pattern_match(occupancy_text, ASSAY_DETECTORS[1][1]):
            return "ChIP-seq"
        return "unknown"

    remaining = " ".join(
        fields.get(key, "")
        for key in ("summary", "platformtitle", "ptechtype")
        if fields.get(key)
    )
    for label, patterns in ASSAY_DETECTORS:
        if _first_pattern_match(remaining, patterns):
            return label

    return "unknown"


def detect_conflicting_assays(fields: dict[str, str], requested_assay: str | None) -> list[str]:
    """Return conflicting assay labels present in metadata for an RNA-seq request."""
    if _normalize_text(requested_assay or "") != "rna-seq":
        return []

    title = fields.get("title", "")
    tagged = _detect_from_title_tags(title)
    if tagged and tagged != "RNA-seq":
        return [tagged]
    if tagged == "RNA-seq":
        return []

    observed = detect_observed_assay(fields)
    if observed in CONFLICTING_ASSAYS_FOR_RNA_SEQ:
        return [observed]
    return []


def _slot_supported_by_observed(slot: str, mapping: ConceptMapping, fields: dict[str, str]) -> bool:
    if slot == "assay":
        observed = detect_observed_assay(fields)
        requested = _normalize_text(mapping.label)
        if observed == "unknown":
            return False
        return _normalize_text(observed) == requested

    if slot == "organism":
        observed = detect_observed_organism(fields, mapping)
        return observed is not None

    return any(
        _term_in_text(term, text)
        for field in SLOT_FIELD_PRIORITY
        for text in [fields.get(field, "")]
        if text
        for term in search_terms_for_mapping(mapping)
    )


def detect_observed_organism(fields: dict[str, str], mapping: ConceptMapping | None = None) -> str | None:
    taxon = fields.get("taxon", "")
    if taxon and (not mapping or _term_in_text(mapping.label, taxon) or any(
        _term_in_text(term, taxon) for term in (search_terms_for_mapping(mapping) if mapping else [])
    )):
        return taxon

    for field in ("title", "summary", "platformtaxa", "sample_titles"):
        text = fields.get(field, "")
        if not text:
            continue
        if mapping:
            if any(_term_in_text(term, text) for term in search_terms_for_mapping(mapping)):
                return mapping.label if field != "taxon" else taxon or mapping.label
        elif _first_pattern_match(text, [r"\bhomo sapiens\b", r"\bhuman\b"]):
            return "Homo sapiens"
    return taxon or None


def detect_observed_disease(fields: dict[str, str], mapping: ConceptMapping | None) -> str | None:
    if not mapping:
        return None
    for field in ("title", "summary"):
        text = fields.get(field, "")
        if text and any(_term_in_text(term, text) for term in search_terms_for_mapping(mapping)):
            return mapping.label
    return None


def detect_observed_tissue(fields: dict[str, str], mapping: ConceptMapping | None) -> str | None:
    if not mapping:
        return None
    for field in ("title", "summary", "sample_titles"):
        text = fields.get(field, "")
        if text and any(_term_in_text(term, text) for term in search_terms_for_mapping(mapping)):
            return mapping.label
    return None


def extract_evidence_for_mapping(
    mapping: ConceptMapping,
    fields: dict[str, str],
) -> tuple[bool, list[EvidenceSnippet]]:
    """Return whether a concept is supported by metadata and supporting snippets."""
    snippets: list[EvidenceSnippet] = []
    search_terms = search_terms_for_mapping(mapping)

    for field in SLOT_FIELD_PRIORITY:
        text = fields.get(field, "")
        if not text:
            continue

        matched_labels = [
            mapping.label
            for term in search_terms
            if _term_in_text(term, text)
        ]
        if mapping.slot == "assay":
            observed = detect_observed_assay(fields)
            if observed != "unknown" and _normalize_text(observed) == _normalize_text(mapping.label):
                matched_labels = [mapping.label]
            else:
                matched_labels = []

        if mapping.slot == "organism" and not matched_labels:
            taxon = fields.get("taxon", "")
            if taxon and any(_term_in_text(term, taxon) for term in search_terms):
                matched_labels = [mapping.label]
                text = taxon
                field = "taxon"

        if matched_labels:
            excerpt = text if len(text) <= 240 else text[:237] + "..."
            snippets.append(
                EvidenceSnippet(
                    field=field,
                    text=excerpt,
                    matched_concepts=sorted(set(matched_labels)),
                )
            )

    supported = _slot_supported_by_observed(mapping.slot, mapping, fields)
    return supported, snippets


def build_observed_metadata(
    fields: dict[str, str],
    concept_mappings: list[ConceptMapping],
) -> dict[str, str | None]:
    """Populate observed facet values from metadata."""
    mapping_by_slot = {mapping.slot: mapping for mapping in concept_mappings}
    return {
        "observed_assay": detect_observed_assay(fields),
        "observed_organism": detect_observed_organism(fields, mapping_by_slot.get("organism")),
        "observed_disease": detect_observed_disease(fields, mapping_by_slot.get("disease")),
        "observed_tissue": detect_observed_tissue(fields, mapping_by_slot.get("tissue")),
    }
