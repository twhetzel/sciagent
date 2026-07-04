"""Base types for ontology grounding providers."""

from __future__ import annotations

from typing import Protocol

from domain.dataset_search import ConceptMapping

FACET_ONTOLOGIES: dict[str, list[str]] = {
    "disease": ["mondo", "hp"],
    "tissue": ["uberon"],
    "assay": ["obi", "go"],
    "organism": ["ncbitaxon"],
}

CONFIDENCE_BY_MATCH: dict[str, float] = {
    "exact": 0.92,
    "synonym": 0.86,
    "curated_exact": 0.78,
    "curated_synonym": 0.74,
    "ai_expanded_synonym": 0.68,
}

SLOT_ONTOLOGY_PREFERENCE: dict[str, list[str]] = {
    "disease": ["MONDO", "HP"],
    "tissue": ["UBERON"],
    "assay": ["OBI", "GO"],
    "organism": ["NCBITAXON"],
}


class OntologyProvider(Protocol):
    """Lookup ontology concepts for a facet term."""

    name: str

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        """Return ranked concept candidates for the slot and query term."""
        ...


def _ontology_preference_rank(slot: str, candidate: ConceptMapping) -> int:
    preferences = SLOT_ONTOLOGY_PREFERENCE.get(slot, [])
    ontology = candidate.ontology.upper()
    for index, prefix in enumerate(preferences):
        if ontology.startswith(prefix):
            return index
    return len(preferences)


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

    def sort_key(item: ConceptMapping) -> tuple[float, int, str]:
        pref = _ontology_preference_rank(slot or item.slot, item)
        return (-item.confidence, pref, item.label.lower())

    return sorted(best_by_curie.values(), key=sort_key)
