"""Extract observed metadata and evidence snippets from dataset records."""

from __future__ import annotations

import re
from typing import Iterable

from .dataset_search import ConceptMapping, EvidenceSnippet
from .synonym_classification import (
    ensure_aliases,
    evidence_terms_for_mapping,
    has_acronym_context,
    term_in_text,
    terms_matching_in_text,
)
from .gxa_assay import (
    GXA_EXPERIMENT_TYPE_FIELD,
    GXA_OBSERVED_ASSAY_FIELD,
    build_gxa_assay_warning,
    gxa_supports_requested_assay,
)
from .omicsdi_assay import (
    OMICSDI_OMICS_TYPE_FIELD,
    OMICSDI_OBSERVED_ASSAY_FIELD,
    omicsdi_supports_requested_assay,
)
from .repository_vocab import resolve_immport_facet_value

DERIVED_TISSUE_MODEL_PATTERNS: tuple[str, ...] = (
    r"\borganoids?\b",
    r"\bcolonoids?\b",
    r"\benteroids?\b",
    r"\bgut organoids?\b",
    r"\bintestinal organoids?\b",
)

DISEASE_EVIDENCE_FIELDS = ("title", "summary", "condition_or_disease")
TISSUE_EVIDENCE_FIELDS = ("title", "summary", "sample_titles", "biosample_type")

# ImmPort Shared Data structured facet fields (also used by other CV-backed sources).
IMMPORT_DISEASE_FIELD = "condition_or_disease"
IMMPORT_TISSUE_FIELD = "biosample_type"
IMMPORT_ASSAY_FIELD = "assay_method"
IMMPORT_STRUCTURED_FACET_FIELDS = (
    IMMPORT_DISEASE_FIELD,
    IMMPORT_TISSUE_FIELD,
    IMMPORT_ASSAY_FIELD,
)

ASSAY_DETECTORS: list[tuple[str, list[str]]] = [
    ("ATAC-seq", [r"\batac[\s-]?seq\b", r"transposase-accessible"]),
    ("ChIP-seq", [r"\bchip[\s-]?seq\b", r"chromatin immunoprecipitation"]),
    ("methylation", [r"\bmethylation\b", r"\bbisulfite\b", r"\b450k\b", r"\be methylation\b"]),
    ("microarray", [r"\bmicroarray\b", r"\baffymetrix\b", r"\bagilent\b.*\barray\b"]),
    (
        "proteomics",
        [
            r"\bproteomic",
            r"\bproteomics\b",
            r"\blc[\s-]?ms/?ms\b",
            r"\blc[\s-]?ms\b",
            r"\bmass spectromet",
        ],
    ),
    (
        "RNA-seq",
        [
            r"\brna[\s-]?seq\b",
            r"\brna sequencing\b",
            r"\brnaseq\b",
            r"\bmrna[\s-]?seq\b",
            r"\btranscriptome profiling\b",
        ],
    ),
    (
        "Flow Cytometry",
        [r"\bflow[\s-]?cytometry\b", r"\bfacs\b"],
    ),
]

GDS_TYPE_ASSAY_HINTS: list[tuple[str, str]] = [
    ("expression profiling by high throughput sequencing", "RNA-seq"),
    ("non-coding rna profiling by high throughput sequencing", "RNA-seq"),
    ("genome binding/occupancy profiling by high throughput sequencing", "occupancy"),
    ("methylation profiling by high throughput sequencing", "methylation"),
    ("array", "microarray"),
    ("flow cytometry", "Flow Cytometry"),
]

STRUCTURED_ASSAY_FIELDS = ("assay_method", "gdstype", "summary", "platformtitle", "ptechtype")
MIXED_ASSAY_LABEL = "mixed or multi-assay"

MOUSE_ORGANISM_LABEL = "Mus musculus"
HUMAN_ORGANISM_LABEL = "Homo sapiens"
STRUCTURED_ORGANISM_FIELDS = ("taxon", "platformtaxa", "sample_titles")
NARRATIVE_ORGANISM_FIELDS = ("title", "summary")

SLOT_FIELD_PRIORITY = (
    "taxon",
    "platformtaxa",
    "sample_titles",
    "gdstype",
    "platformtitle",
    "ptechtype",
    "title",
    "summary",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _split_facet_values(text: str) -> list[str]:
    """Split comma- or semicolon-separated controlled vocabulary values."""
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;]", text) if part.strip()]


def _structured_facet_matches_mapping(mapping: ConceptMapping, text: str) -> bool:
    """Match a repository CV facet value against a grounded concept mapping."""
    if not text:
        return False
    fragments = _split_facet_values(text) or [text.strip()]
    requested_values = {
        _normalize_text(mapping.label),
        _normalize_text(mapping.query_term),
    }
    resolved_request = resolve_immport_facet_value(mapping.slot, mapping.label)
    if resolved_request:
        requested_values.add(_normalize_text(resolved_request))
    for synonym in mapping.synonyms or []:
        requested_values.add(_normalize_text(synonym))
        resolved_synonym = resolve_immport_facet_value(mapping.slot, synonym)
        if resolved_synonym:
            requested_values.add(_normalize_text(resolved_synonym))
    requested_values.discard("")

    for fragment in fragments:
        if terms_matching_in_text(mapping, fragment):
            return True
        fragment_norm = _normalize_text(fragment)
        if fragment_norm in requested_values:
            return True
        resolved_fragment = resolve_immport_facet_value(mapping.slot, fragment)
        if resolved_fragment and _normalize_text(resolved_fragment) in requested_values:
            return True
    return False


def _structured_matched_terms(mapping: ConceptMapping, text: str) -> list[str]:
    """Return CV fragment labels that matched a grounded concept."""
    matched: list[str] = []
    for fragment in _split_facet_values(text) or [text.strip()]:
        if _structured_facet_matches_mapping(mapping, fragment):
            matched.append(fragment)
    if matched:
        return matched
    if _structured_facet_matches_mapping(mapping, text):
        return [text.strip()]
    return []


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


def _assays_in_text(text: str, field_name: str = "") -> set[str]:
    assays: set[str] = set()
    if not text:
        return assays

    if field_name == "title":
        tagged = _detect_from_title_tags(text)
        if tagged:
            assays.add(tagged)

    if field_name == "gdstype":
        normalized = _normalize_text(text)
        for hint, assay in GDS_TYPE_ASSAY_HINTS:
            if hint in normalized:
                if assay == "occupancy":
                    occupancy_text = normalized
                    if _first_pattern_match(occupancy_text, ASSAY_DETECTORS[0][1]):
                        assays.add("ATAC-seq")
                    elif _first_pattern_match(occupancy_text, ASSAY_DETECTORS[1][1]):
                        assays.add("ChIP-seq")
                    else:
                        assays.add("occupancy")
                else:
                    assays.add(assay)

    if field_name == IMMPORT_ASSAY_FIELD:
        for value in _split_facet_values(text):
            assays.add(value)

    for label, patterns in ASSAY_DETECTORS:
        if _first_pattern_match(text, patterns):
            assays.add(label)

    return assays


def detect_assays_by_field(fields: dict[str, str]) -> dict[str, set[str]]:
    """Detect assay labels mentioned in each metadata field."""
    by_field: dict[str, set[str]] = {}
    for field_name, text in fields.items():
        assays = _assays_in_text(text, field_name=field_name)
        if assays:
            by_field[field_name] = assays
    return by_field


def detect_observed_assay(fields: dict[str, str]) -> str:
    """Summarize assay type from returned metadata only (never from the user query)."""
    gxa_observed = fields.get(GXA_OBSERVED_ASSAY_FIELD, "").strip()
    if gxa_observed:
        return gxa_observed

    omicsdi_observed = fields.get(OMICSDI_OBSERVED_ASSAY_FIELD, "").strip()
    if omicsdi_observed:
        return omicsdi_observed

    assay_method = fields.get(IMMPORT_ASSAY_FIELD, "").strip()
    if assay_method:
        values = _split_facet_values(assay_method)
        if len(values) == 1:
            return values[0]
        if len(values) > 1:
            return MIXED_ASSAY_LABEL

    by_field = detect_assays_by_field(fields)
    all_assays: set[str] = set()
    for assays in by_field.values():
        all_assays.update(assays)

    concrete = {assay for assay in all_assays if assay != "occupancy"}
    if len(concrete) > 1:
        return MIXED_ASSAY_LABEL
    if len(concrete) == 1:
        return next(iter(concrete))
    if "occupancy" in all_assays:
        return "unknown"
    return "unknown"


def _assay_supported_in_field(mapping: ConceptMapping, field_name: str, text: str) -> bool:
    if mapping.slot != "assay":
        return False
    if field_name == IMMPORT_ASSAY_FIELD and _structured_facet_matches_mapping(mapping, text):
        return True
    requested = _normalize_text(mapping.label)
    field_assays = _assays_in_text(text, field_name=field_name)
    return any(_normalize_text(assay) == requested for assay in field_assays)


def _assay_evidence_fields(fields: dict[str, str], mapping: ConceptMapping) -> list[tuple[str, str]]:
    """Return fields that explicitly support the requested assay in returned metadata."""
    gxa_type = fields.get(GXA_EXPERIMENT_TYPE_FIELD, "").strip()
    if gxa_type:
        if gxa_supports_requested_assay(gxa_type, mapping.label):
            return [(GXA_EXPERIMENT_TYPE_FIELD, gxa_type)]
        return []

    omics_type = fields.get(OMICSDI_OMICS_TYPE_FIELD, "").strip()
    assay_method = fields.get(IMMPORT_ASSAY_FIELD, "").strip()
    if omics_type or assay_method:
        if omicsdi_supports_requested_assay(
            omics_type=omics_type,
            assay_method=assay_method,
            requested_label=mapping.label,
        ):
            if omics_type:
                return [(OMICSDI_OMICS_TYPE_FIELD, omics_type)]
            return [(IMMPORT_ASSAY_FIELD, assay_method)]
        if omics_type:
            return []

    assay_method = fields.get(IMMPORT_ASSAY_FIELD, "").strip()
    if assay_method and _structured_facet_matches_mapping(mapping, assay_method):
        return [(IMMPORT_ASSAY_FIELD, assay_method)]

    matches: list[tuple[str, str]] = []
    for field_name in SLOT_FIELD_PRIORITY:
        text = fields.get(field_name, "")
        if text and _assay_supported_in_field(mapping, field_name, text):
            matches.append((field_name, text))
    return matches


def detect_evidence_conflicts(
    fields: dict[str, str],
    mapping_by_slot: dict[str, ConceptMapping],
) -> list[str]:
    """Describe disagreements between metadata fields without changing the score."""
    conflicts: list[str] = []
    by_field = detect_assays_by_field(fields)
    assay_mapping = mapping_by_slot.get("assay")

    title_assays = by_field.get("title", set())
    structured_assays: set[str] = set()
    for field_name in STRUCTURED_ASSAY_FIELDS:
        structured_assays.update(by_field.get(field_name, set()))
    structured_assays.discard("occupancy")

    if assay_mapping and _normalize_text(assay_mapping.label) == "rna-seq":
        structured_rna = "RNA-seq" in structured_assays
        title_non_rna = title_assays - {"RNA-seq"}
        if structured_rna and title_non_rna:
            title_label = ", ".join(sorted(title_non_rna))
            conflicts.append(
                "Possible assay conflict: title mentions "
                f"{title_label} while metadata/search evidence indicates RNA-seq."
            )

    all_concrete: set[str] = set()
    for assays in by_field.values():
        all_concrete.update(assay for assay in assays if assay != "occupancy")
    if len(all_concrete) > 1 and assay_mapping:
        requested = _normalize_text(assay_mapping.label)
        requested_present = any(_normalize_text(assay) == requested for assay in all_concrete)
        if not requested_present:
            conflicts.append(
                "Multiple assay types detected across metadata fields: "
                f"{', '.join(sorted(all_concrete))}."
            )

    return conflicts


def build_metadata_warnings(
    fields: dict[str, str],
    mapping_by_slot: dict[str, ConceptMapping],
    observed_assay: str,
) -> list[str]:
    """User-facing warnings about ambiguity or disagreement in repository metadata."""
    warnings = list(detect_evidence_conflicts(fields, mapping_by_slot))

    by_field = detect_assays_by_field(fields)
    all_concrete: set[str] = set()
    for assays in by_field.values():
        all_concrete.update(assay for assay in assays if assay != "occupancy")
    if len(all_concrete) > 1:
        warnings.append(
            "Multiple assay types detected across metadata fields: "
            f"{', '.join(sorted(all_concrete))}."
        )

    if observed_assay == MIXED_ASSAY_LABEL:
        warnings.append(
            "Metadata appears to include multiple assay types; labeled as mixed or multi-assay."
        )

    assay_mapping = mapping_by_slot.get("assay")
    if assay_mapping:
        gxa_warning = build_gxa_assay_warning(fields, assay_mapping)
        if gxa_warning:
            warnings.append(gxa_warning)

        has_assay_evidence = bool(_assay_evidence_fields(fields, assay_mapping))
        if not has_assay_evidence and not gxa_warning:
            warnings.append(
                f"No returned metadata field explicitly supports requested {assay_mapping.label}."
            )

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            unique.append(warning)
    return unique


def _slot_supported_by_evidence(slot: str, mapping: ConceptMapping, fields: dict[str, str]) -> bool:
    if slot == "assay":
        return bool(_assay_evidence_fields(fields, mapping))

    if slot == "organism":
        supported, _, _ = organism_supported_by_evidence(fields, mapping)
        return supported

    if slot == "disease":
        return detect_observed_disease(fields, mapping) is not None

    if slot == "tissue":
        return detect_observed_tissue(fields, mapping) is not None

    return any(
        bool(terms_matching_in_text(mapping, text))
        for field in SLOT_FIELD_PRIORITY
        for text in [fields.get(field, "")]
        if text
    )


def _is_mouse_text(text: str) -> bool:
    normalized = _normalize_text(text)
    return (
        "mus musculus" in normalized
        or re.search(r"\bmouse\b|\bmice\b|\bmurine\b", normalized) is not None
    )


def _is_human_text(text: str) -> bool:
    normalized = _normalize_text(text)
    return "homo sapiens" in normalized or re.search(r"\bhuman\b", normalized) is not None


def detect_structured_organism(fields: dict[str, str]) -> str | None:
    """Return organism from structured taxon/sample metadata only."""
    for field in STRUCTURED_ORGANISM_FIELDS:
        text = fields.get(field, "")
        if not text:
            continue
        if _is_mouse_text(text):
            return MOUSE_ORGANISM_LABEL
        if _is_human_text(text):
            return HUMAN_ORGANISM_LABEL
        return text.strip()
    return None


def detect_narrative_organism(fields: dict[str, str]) -> str | None:
    """Return organism hints from title/summary when structured taxon is absent."""
    for field in NARRATIVE_ORGANISM_FIELDS:
        text = fields.get(field, "")
        if not text:
            continue
        if _is_mouse_text(text):
            return MOUSE_ORGANISM_LABEL
        if _is_human_text(text):
            return HUMAN_ORGANISM_LABEL
    return None


def _organism_matches_mapping(observed: str, mapping: ConceptMapping) -> bool:
    if mapping.slot != "organism":
        return False
    return any(term_in_text(term, observed) for term in evidence_terms_for_mapping(mapping))


def organism_supported_by_evidence(
    fields: dict[str, str],
    mapping: ConceptMapping,
) -> tuple[bool, str | None, str | None]:
    """
    Determine whether organism evidence supports the requested concept.

    Returns (supported, observed_label, evidence_field).
    """
    structured = detect_structured_organism(fields)
    if structured:
        if _organism_matches_mapping(structured, mapping):
            field = next(
                (name for name in STRUCTURED_ORGANISM_FIELDS if fields.get(name)),
                "taxon",
            )
            return True, structured, field
        return False, structured, None

    narrative = detect_narrative_organism(fields)
    if narrative and _organism_matches_mapping(narrative, mapping):
        field = next(
            (name for name in NARRATIVE_ORGANISM_FIELDS if fields.get(name)),
            "title",
        )
        return True, narrative, field

    return False, narrative or structured, None


def detect_mouse_model_of_human_disease(
    fields: dict[str, str],
    disease_mapping: ConceptMapping | None,
) -> tuple[bool, str]:
    """Detect mouse model studies where human disease language appears in metadata."""
    structured = detect_structured_organism(fields)
    if not structured or not _is_mouse_text(structured):
        return False, ""

    if disease_mapping and detect_observed_disease(fields, disease_mapping):
        return True, (
            "Mouse model study (Mus musculus); human disease terms appear in metadata "
            "but organism is not Homo sapiens."
        )

    for field in NARRATIVE_ORGANISM_FIELDS:
        text = fields.get(field, "")
        if text and _is_human_text(text):
            return True, (
                "Metadata mentions human disease context, but structured organism metadata "
                "indicates Mus musculus (likely an animal model study)."
            )

    return False, ""


def detect_observed_organism(fields: dict[str, str], mapping: ConceptMapping | None = None) -> str | None:
    structured = detect_structured_organism(fields)
    if structured:
        return structured

    narrative = detect_narrative_organism(fields)
    if narrative:
        return narrative

    del mapping
    return None


def _matched_terms_in_fields(
    mapping: ConceptMapping,
    fields: dict[str, str],
    field_names: tuple[str, ...],
) -> tuple[bool, list[str], list[str]]:
    matched_fields: list[str] = []
    matched_terms: set[str] = set()
    for field_name in field_names:
        text = fields.get(field_name, "")
        if not text:
            continue
        if field_name in IMMPORT_STRUCTURED_FACET_FIELDS:
            if _structured_facet_matches_mapping(mapping, text):
                matched_fields.append(field_name)
                matched_terms.update(_structured_matched_terms(mapping, text))
            continue
        terms = terms_matching_in_text(mapping, text)
        if terms:
            matched_fields.append(field_name)
            matched_terms.update(terms)
    return bool(matched_fields), matched_fields, sorted(matched_terms)


def _has_derived_tissue_model_signal(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(re.search(pattern, normalized, re.I) for pattern in DERIVED_TISSUE_MODEL_PATTERNS)


def _tissue_match_is_contextual_only(
    mapping: ConceptMapping,
    fields: dict[str, str],
    evidence_fields: list[str],
) -> bool:
    enriched = ensure_aliases(mapping)
    found_contextual = False
    for field_name in evidence_fields:
        text = fields.get(field_name, "")
        if not text:
            continue
        for alias in enriched.aliases:
            if alias.safe_for_retrieval and term_in_text(alias.term, text):
                return False
        for alias in enriched.aliases:
            if alias.requires_context and term_in_text(alias.term, text):
                if has_acronym_context(text, enriched):
                    found_contextual = True
    return found_contextual


def extract_disease_evidence_details(
    mapping: ConceptMapping | None,
    fields: dict[str, str],
) -> tuple[bool, list[str], list[str]]:
    if not mapping:
        return False, [], []
    return _matched_terms_in_fields(mapping, fields, DISEASE_EVIDENCE_FIELDS)


def extract_tissue_evidence_details(
    mapping: ConceptMapping | None,
    fields: dict[str, str],
) -> tuple[bool, list[str], list[str], str]:
    if not mapping:
        return False, [], [], "absent"

    present, matched_fields, matched_terms = _matched_terms_in_fields(
        mapping,
        fields,
        TISSUE_EVIDENCE_FIELDS,
    )
    if not present:
        return False, [], [], "absent"

    evidence_text = " ".join(fields.get(field_name, "") for field_name in matched_fields)
    if _has_derived_tissue_model_signal(evidence_text):
        return present, matched_fields, matched_terms, "derived_model"

    direct_fields = {"title", "summary", IMMPORT_TISSUE_FIELD}
    if matched_fields and not any(field in direct_fields for field in matched_fields):
        return present, matched_fields, matched_terms, "ambiguous"

    if _tissue_match_is_contextual_only(mapping, fields, matched_fields):
        return present, matched_fields, matched_terms, "ambiguous"

    return present, matched_fields, matched_terms, "direct"


def extract_assay_evidence_details(
    mapping: ConceptMapping | None,
    fields: dict[str, str],
) -> tuple[bool, list[str], list[str]]:
    if not mapping:
        return False, [], []

    matches = _assay_evidence_fields(fields, mapping)
    if not matches:
        return False, [], []

    matched_fields = [field_name for field_name, _ in matches]
    requested = _normalize_text(mapping.label)
    matched_terms: set[str] = set()
    for field_name, text in matches:
        if field_name == IMMPORT_ASSAY_FIELD:
            for value in _split_facet_values(text):
                if _structured_facet_matches_mapping(mapping, value):
                    matched_terms.add(value)
            continue
        for assay in _assays_in_text(text, field_name=field_name):
            if _normalize_text(assay) == requested:
                matched_terms.add(assay)
    if not matched_terms:
        matched_terms.add(mapping.label)
    return True, matched_fields, sorted(matched_terms)


def extract_organism_evidence_details(
    mapping: ConceptMapping | None,
    fields: dict[str, str],
) -> tuple[bool, list[str], list[str], str]:
    if not mapping:
        return False, [], [], "absent"

    supported, observed, evidence_field = organism_supported_by_evidence(fields, mapping)
    if not supported or not evidence_field:
        return False, [], [], "absent"

    evidence_source = (
        "structured"
        if evidence_field in STRUCTURED_ORGANISM_FIELDS
        else "narrative"
    )
    text = fields.get(evidence_field, "")
    matched_terms = sorted(
        {
            term
            for term in evidence_terms_for_mapping(mapping)
            if term_in_text(term, text)
        }
    )
    if observed:
        matched_terms = sorted(set(matched_terms) | {_normalize_text(observed)})
    return True, [evidence_field], matched_terms, evidence_source


def detect_observed_disease(fields: dict[str, str], mapping: ConceptMapping | None) -> str | None:
    if not mapping:
        return None
    structured = fields.get(IMMPORT_DISEASE_FIELD, "")
    if structured and _structured_facet_matches_mapping(mapping, structured):
        for fragment in _structured_matched_terms(mapping, structured):
            return fragment
    for field in ("title", "summary"):
        text = fields.get(field, "")
        if text and terms_matching_in_text(mapping, text):
            return mapping.label
    return None


def detect_observed_tissue(fields: dict[str, str], mapping: ConceptMapping | None) -> str | None:
    if not mapping:
        return None
    structured = fields.get(IMMPORT_TISSUE_FIELD, "")
    if structured and _structured_facet_matches_mapping(mapping, structured):
        for fragment in _structured_matched_terms(mapping, structured):
            return fragment
    for field in ("title", "summary", "sample_titles"):
        text = fields.get(field, "")
        if text and terms_matching_in_text(mapping, text):
            return mapping.label
    return None


def extract_evidence_for_mapping(
    mapping: ConceptMapping,
    fields: dict[str, str],
) -> tuple[bool, list[EvidenceSnippet]]:
    """Return whether a concept is supported by metadata and supporting snippets."""
    snippets: list[EvidenceSnippet] = []

    if mapping.slot == "assay":
        for field_name, text in _assay_evidence_fields(fields, mapping):
            excerpt = text if len(text) <= 240 else text[:237] + "..."
            snippets.append(
                EvidenceSnippet(
                    field=field_name,
                    text=excerpt,
                    matched_concepts=[mapping.label],
                )
            )
        return bool(snippets), snippets

    if mapping.slot == "organism":
        supported, observed, evidence_field = organism_supported_by_evidence(fields, mapping)
        if supported and evidence_field:
            text = fields.get(evidence_field, "")
            excerpt = text if len(text) <= 240 else text[:237] + "..."
            snippets.append(
                EvidenceSnippet(
                    field=evidence_field,
                    text=excerpt,
                    matched_concepts=[observed or mapping.label],
                )
            )
        return supported, snippets

    for field in SLOT_FIELD_PRIORITY:
        text = fields.get(field, "")
        if not text:
            continue

        if terms_matching_in_text(mapping, text):
            matched_labels = [mapping.label]
            excerpt = text if len(text) <= 240 else text[:237] + "..."
            snippets.append(
                EvidenceSnippet(
                    field=field,
                    text=excerpt,
                    matched_concepts=sorted(set(matched_labels)),
                )
            )

    supported = _slot_supported_by_evidence(mapping.slot, mapping, fields)
    return supported, snippets


def build_observed_metadata(
    fields: dict[str, str],
    concept_mappings: list[ConceptMapping],
) -> dict[str, str | None]:
    """Populate observed facet values from returned metadata only."""
    mapping_by_slot = {mapping.slot: mapping for mapping in concept_mappings}
    return {
        "observed_assay": detect_observed_assay(fields),
        "observed_organism": detect_observed_organism(fields, mapping_by_slot.get("organism")),
        "observed_disease": detect_observed_disease(fields, mapping_by_slot.get("disease")),
        "observed_tissue": detect_observed_tissue(fields, mapping_by_slot.get("tissue")),
    }
