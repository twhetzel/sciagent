"""Ontology grounding orchestrator for dataset discovery."""

from __future__ import annotations

from domain.dataset_search import ConceptMapping, InterpretedQuery
from domain.ontology_providers.base import OntologyProvider, merge_concept_candidates
from domain.ontology_providers.bioportal import BioPortalProvider
from domain.ontology_providers.curated import CuratedAliasProvider
from domain.ontology_providers.llm import LLMDisambiguationProvider
from domain.ontology_providers.ols import OLSProvider

DEFAULT_PROVIDERS: tuple[str, ...] = ("ols", "bioportal", "llm_disambiguation", "curated")
STRONG_MATCH_CONFIDENCE = 0.85


def default_providers() -> list[OntologyProvider]:
    return [
        OLSProvider(),
        BioPortalProvider(),
        LLMDisambiguationProvider(),
        CuratedAliasProvider(),
    ]


class OntologyGrounder:
    """Ground facet terms to ontology concepts using ordered providers."""

    def __init__(self, providers: list[OntologyProvider] | None = None) -> None:
        self.providers = providers or default_providers()
        self._cache: dict[tuple[str, str], list[ConceptMapping]] = {}

    def ground(self, slot: str, term: str, top_k: int = 5) -> list[ConceptMapping]:
        """Return ranked concept candidates for one facet term."""
        cache_key = (slot, term.lower())
        if cache_key in self._cache:
            return self._cache[cache_key][:top_k]

        collected: list[ConceptMapping] = []
        for provider in self.providers:
            if provider.name == "llm_disambiguation" and collected:
                best_confidence = max(item.confidence for item in collected)
                if best_confidence >= STRONG_MATCH_CONFIDENCE:
                    continue

            try:
                collected.extend(provider.lookup(slot, term))
            except Exception:
                continue

            merged = merge_concept_candidates(collected)
            if provider.name in {"ols", "bioportal"} and merged and merged[0].confidence >= STRONG_MATCH_CONFIDENCE:
                break

        ranked = merge_concept_candidates(collected)[:top_k]
        self._cache[cache_key] = ranked
        return ranked

    def ground_interpreted_query(self, interpreted: InterpretedQuery) -> list[ConceptMapping]:
        """Pick the top grounded concept for each interpreted facet."""
        mappings: list[ConceptMapping] = []
        slot_values = [
            ("disease", interpreted.disease),
            ("tissue", interpreted.tissue),
            ("assay", interpreted.assay),
            ("organism", interpreted.organism),
        ]
        for slot, term in slot_values:
            if not term:
                continue
            candidates = self.ground(slot, term, top_k=1)
            if candidates:
                mappings.append(candidates[0])
        return mappings
