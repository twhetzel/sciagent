"""Score dataset candidates by evidence-backed ontology concept matches."""

from __future__ import annotations

from .dataset_search import ConceptMapping, DatasetCandidate, EvidenceSnippet
from .evidence_extraction import (
    build_observed_metadata,
    detect_conflicting_assays,
    extract_evidence_for_mapping,
)

SLOT_WEIGHTS = {
    "disease": 0.30,
    "tissue": 0.25,
    "assay": 0.25,
    "organism": 0.10,
    "evidence_coverage": 0.10,
}

ASSAY_CONFLICT_PENALTY = 0.35


def rank_dataset_candidates(
    candidates: list[DatasetCandidate],
    concept_mappings: list[ConceptMapping],
    requested_assay: str | None = None,
) -> list[DatasetCandidate]:
    """Score and sort candidates using metadata evidence only."""
    ranked: list[DatasetCandidate] = []
    expected_slots = {mapping.slot for mapping in concept_mappings}

    for candidate in candidates:
        fields = candidate.metadata_fields or {
            "title": candidate.title,
            "summary": candidate.description,
        }
        observed = build_observed_metadata(fields, concept_mappings)
        conflicting = detect_conflicting_assays(fields, requested_assay)

        slot_hits: dict[str, bool] = {}
        matched_concepts: list[ConceptMapping] = []
        evidence_snippets: list[EvidenceSnippet] = []
        why_matched: list[str] = []
        why_partial: list[str] = []

        for mapping in concept_mappings:
            supported, snippets = extract_evidence_for_mapping(mapping, fields)
            slot_hits[mapping.slot] = supported
            if supported:
                matched_concepts.append(mapping)
                why_matched.append(
                    f"{mapping.slot}: supported by metadata as {mapping.label} ({mapping.curie})"
                )
                evidence_snippets.extend(snippets)
            else:
                if mapping.slot == "assay":
                    observed_assay = observed["observed_assay"]
                    if conflicting:
                        why_partial.append(
                            f"assay: metadata indicates {', '.join(conflicting)}, not requested {mapping.label}"
                        )
                    elif observed_assay and observed_assay != "unknown":
                        why_partial.append(
                            f"assay: observed {observed_assay}, requested {mapping.label}"
                        )
                    else:
                        why_partial.append(
                            f"assay: no RNA-seq evidence in title, summary, or experiment type"
                        )
                else:
                    why_partial.append(
                        f"{mapping.slot}: requested {mapping.label}, not supported by returned metadata"
                    )

        slot_score = sum(
            SLOT_WEIGHTS[slot]
            for slot, hit in slot_hits.items()
            if hit and slot in SLOT_WEIGHTS
        )
        covered = sum(1 for slot in expected_slots if slot_hits.get(slot))
        evidence_coverage = covered / len(expected_slots) if expected_slots else 0.0
        score = slot_score + (SLOT_WEIGHTS["evidence_coverage"] * evidence_coverage)

        if conflicting:
            score = max(0.0, score - ASSAY_CONFLICT_PENALTY)

        if conflicting:
            match_status = "conflict"
        elif covered == len(expected_slots) and expected_slots:
            match_status = "full"
        else:
            match_status = "partial"

        ranked.append(
            candidate.model_copy(
                update={
                    "requested_concepts": list(concept_mappings),
                    "matched_concepts": matched_concepts,
                    "observed_assay": observed["observed_assay"],
                    "observed_organism": observed["observed_organism"],
                    "observed_disease": observed["observed_disease"],
                    "observed_tissue": observed["observed_tissue"],
                    "evidence_snippets": evidence_snippets,
                    "score": round(score, 3),
                    "match_status": match_status,
                    "why_matched": why_matched,
                    "why_partial": why_partial,
                    "conflicting_assays": conflicting,
                }
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.accession))
    return ranked
