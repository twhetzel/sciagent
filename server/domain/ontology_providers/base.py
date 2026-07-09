"""Base types for ontology grounding providers."""

from __future__ import annotations

from typing import Any, Protocol

from domain.dataset_search import ConceptMapping

from .obo_foundry_policy import (
    FACET_ONTOLOGIES,
    SLOT_CURIE_PREFIXES,
    SLOT_FALLBACK_ONTOLOGIES,
    SLOT_ONTOLOGY_PREFERENCE,
    SLOT_PRIMARY_ONTOLOGIES,
)

CONFIDENCE_BY_MATCH: dict[str, float] = {
    "exact": 0.92,
    "synonym": 0.86,
    "curated_exact": 0.78,
    "curated_synonym": 0.74,
    "ai_expanded_synonym": 0.68,
}


class OntologyProvider(Protocol):
    """Lookup ontology concepts for a facet term."""

    name: str

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        """Return ranked concept candidates for the slot and query term."""
        ...


def ontology_tier(slot: str, candidate: ConceptMapping) -> int:
    """
    Return ontology priority tier for facet-aware candidate selection.

    Tier 0 = primary ontologies for the facet (OBO Foundry domain-aligned).
    Tier 1 = fallback-only ontologies (e.g. HP for disease).
    Tier 2 = everything else.
    """
    ontology = candidate.ontology.upper()
    for prefix in SLOT_PRIMARY_ONTOLOGIES.get(slot, []):
        if ontology.startswith(prefix):
            return 0
    for prefix in SLOT_FALLBACK_ONTOLOGIES.get(slot, []):
        if ontology.startswith(prefix):
            return 1
    return 2


def is_primary_tier_match(slot: str, candidate: ConceptMapping) -> bool:
    """Return True when a candidate is from a primary ontology for the facet."""
    return ontology_tier(slot, candidate) == 0


def _ontology_preference_rank(slot: str, candidate: ConceptMapping) -> int:
    preferences = SLOT_ONTOLOGY_PREFERENCE.get(slot, [])
    ontology = candidate.ontology.upper()
    for index, prefix in enumerate(preferences):
        if ontology.startswith(prefix):
            return index
    return len(preferences)


def _candidate_sort_key(slot: str, candidate: ConceptMapping) -> tuple[int, float, int, str]:
    return (
        ontology_tier(slot, candidate),
        -candidate.confidence,
        _ontology_preference_rank(slot, candidate),
        candidate.label.lower(),
    )


def rejected_candidate_debug(candidate: ConceptMapping) -> dict[str, Any]:
    """Serialize one non-selected grounding candidate for debug output."""
    return {
        "curie": candidate.curie,
        "label": candidate.label,
        "ontology": candidate.ontology,
        "match_type": candidate.match_type,
        "source": candidate.source,
        "confidence": candidate.confidence,
        "ontology_tier": ontology_tier(candidate.slot, candidate),
    }


def merge_concept_candidates(
    candidates: list[ConceptMapping],
    *,
    slot: str | None = None,
) -> list[ConceptMapping]:
    """Deduplicate by CURIE, keeping the highest-confidence mapping."""
    best_by_curie: dict[str, ConceptMapping] = {}
    for candidate in candidates:
        existing = best_by_curie.get(candidate.curie)
        if existing is None or candidate.confidence > existing.confidence:
            best_by_curie[candidate.curie] = candidate

    resolved_slot = slot or next(iter(best_by_curie.values())).slot if best_by_curie else ""
    return sorted(
        best_by_curie.values(),
        key=lambda item: _candidate_sort_key(resolved_slot, item),
    )


def select_concept_with_debug(
    candidates: list[ConceptMapping],
    *,
    slot: str,
) -> ConceptMapping | None:
    """Pick the best facet-aware candidate and attach rejected alternatives."""
    ranked = merge_concept_candidates(candidates, slot=slot)
    if not ranked:
        return None

    primary = [candidate for candidate in ranked if ontology_tier(slot, candidate) == 0]
    fallback = [candidate for candidate in ranked if ontology_tier(slot, candidate) == 1]
    if primary:
        selected = primary[0]
        pool_label = "primary"
    elif fallback:
        selected = fallback[0]
        pool_label = "fallback"
    else:
        selected = ranked[0]
        pool_label = "other"

    rejected = [candidate for candidate in ranked if candidate.curie != selected.curie]
    reason = (
        f"Selected {selected.ontology} ({selected.curie}) from {pool_label} ontology tier "
        f"via {selected.source} {selected.match_type} match"
    )
    if rejected:
        top_rejected = rejected[0]
        reason += (
            f"; rejected {top_rejected.ontology} ({top_rejected.curie}) "
            f"from {top_rejected.source} ({top_rejected.match_type}, "
            f"confidence={top_rejected.confidence:.2f}, tier={ontology_tier(slot, top_rejected)})"
        )

    return selected.model_copy(
        update={
            "selection_reason": reason,
            "rejected_candidates": [
                rejected_candidate_debug(candidate) for candidate in rejected[:8]
            ],
        }
    )
