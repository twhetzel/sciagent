"""Field-level evidence annotation for dataset discovery candidates."""

from __future__ import annotations

from .assay_ranking import detect_assay_mismatch
from .dataset_search import ConceptMapping, DatasetCandidate, EvidenceSnippet
from .evidence_extraction import (
    build_metadata_warnings,
    build_observed_metadata,
    detect_mouse_model_of_human_disease,
    extract_evidence_for_mapping,
)
from .gxa_assay import build_gxa_assay_warning


def annotate_dataset_candidates(
    candidates: list[DatasetCandidate],
    concept_mappings: list[ConceptMapping],
) -> list[DatasetCandidate]:
    """
    Annotate Evidence: identify metadata-supported concepts and collect snippets.

    This is field-level concept/evidence matching on returned repository records.
    It does not score or rank candidates and does not use ontology_normalizer.py.
    """
    mapping_by_slot = {mapping.slot: mapping for mapping in concept_mappings}
    annotated: list[DatasetCandidate] = []

    for candidate in candidates:
        fields = candidate.metadata_fields or {
            "title": candidate.title,
            "summary": candidate.description,
        }
        observed = build_observed_metadata(fields, concept_mappings)
        metadata_warnings = build_metadata_warnings(
            fields,
            mapping_by_slot,
            observed["observed_assay"] or "unknown",
        )
        is_model, model_warning = detect_mouse_model_of_human_disease(
            fields,
            mapping_by_slot.get("disease"),
        )
        if is_model and model_warning:
            metadata_warnings.append(model_warning)
        evidence_conflicts = [
            warning
            for warning in metadata_warnings
            if "conflict" in warning.lower()
        ]

        matched_concepts: list[ConceptMapping] = []
        evidence_snippets: list[EvidenceSnippet] = []
        why_matched: list[str] = []
        why_partial: list[str] = []

        for mapping in concept_mappings:
            supported, snippets = extract_evidence_for_mapping(mapping, fields)
            if supported:
                matched_concepts.append(mapping)
                why_matched.append(
                    f"{mapping.slot}: supported by returned metadata as {mapping.label} ({mapping.curie})"
                )
                evidence_snippets.extend(snippets)
            else:
                if mapping.slot == "assay":
                    gxa_message = build_gxa_assay_warning(fields, mapping)
                    if gxa_message:
                        why_partial.append(gxa_message)
                        continue
                if mapping.slot == "organism" and is_model:
                    why_partial.append(
                        f"{mapping.slot}: requested {mapping.label}, but structured metadata indicates Mus musculus (animal model)"
                    )
                else:
                    why_partial.append(
                        f"{mapping.slot}: requested {mapping.label}, not supported by returned metadata"
                    )

        match_status = "model" if is_model else candidate.match_status
        assay_mapping = mapping_by_slot.get("assay")
        assay_mismatch, _ = detect_assay_mismatch(
            assay_mapping,
            observed["observed_assay"],
            accession=candidate.accession,
        )

        annotated.append(
            candidate.model_copy(
                update={
                    "requested_concepts": list(concept_mappings),
                    "matched_concepts": matched_concepts,
                    "observed_assay": observed["observed_assay"],
                    "assay_mismatch": assay_mismatch,
                    "observed_organism": observed["observed_organism"],
                    "observed_disease": observed["observed_disease"],
                    "observed_tissue": observed["observed_tissue"],
                    "evidence_snippets": evidence_snippets,
                    "why_matched": why_matched,
                    "why_partial": why_partial,
                    "metadata_warnings": metadata_warnings,
                    "evidence_conflicts": evidence_conflicts,
                    "match_status": match_status,
                }
            )
        )

    return annotated
