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


class OntologyProvider(Protocol):
    """Lookup ontology concepts for a facet term."""

    name: str

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        """Return ranked concept candidates for the slot and query term."""
        ...


def merge_concept_candidates(candidates: list[ConceptMapping]) -> list[ConceptMapping]:
    """Deduplicate by CURIE, keeping the highest-confidence mapping."""
    best_by_curie: dict[str, ConceptMapping] = {}
    for candidate in candidates:
        existing = best_by_curie.get(candidate.curie)
        if existing is None or candidate.confidence > existing.confidence:
            best_by_curie[candidate.curie] = candidate
    return sorted(best_by_curie.values(), key=lambda item: (-item.confidence, item.label))
