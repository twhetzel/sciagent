"""Shared facet search strategies for repository dataset discovery."""

from __future__ import annotations

from .dataset_search import ConceptMapping, InterpretedQuery

# Ordered from strictest to broadest. Used by GEO and Expression Atlas retrieval.
FACET_SEARCH_STRATEGIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("strict", ("disease", "assay", "tissue")),
    ("broad_1", ("disease", "assay")),
    ("broad_2", ("disease", "tissue")),
    ("broad_3", ("disease",)),
)

STRATEGY_PRIORITY = {
    "strict": 0,
    "broad_1": 1,
    "broad_2": 2,
    "broad_3": 3,
}


def _facet_terms(
    *,
    interpreted: InterpretedQuery | None = None,
    concept_mappings: list[ConceptMapping] | None = None,
) -> dict[str, str | None]:
    by_slot = {mapping.slot: mapping.label for mapping in (concept_mappings or [])}
    return {
        "disease": by_slot.get("disease") or (interpreted.disease if interpreted else None),
        "tissue": by_slot.get("tissue") or (interpreted.tissue if interpreted else None),
        "assay": by_slot.get("assay") or (interpreted.assay if interpreted else None),
    }


def build_facet_search_queries(
    *,
    interpreted: InterpretedQuery | None = None,
    concept_mappings: list[ConceptMapping] | None = None,
) -> list[tuple[str, str]]:
    """Build multi-strategy plain-text queries from interpreted and/or grounded facets."""
    facets = _facet_terms(interpreted=interpreted, concept_mappings=concept_mappings)
    queries: list[tuple[str, str]] = []

    for strategy, slots in FACET_SEARCH_STRATEGIES:
        terms = [facets[slot] for slot in slots if facets.get(slot)]
        if not terms:
            continue
        queries.append((strategy, " ".join(terms)))

    return queries


def build_interpreted_facet_queries(
    interpreted: InterpretedQuery,
) -> list[tuple[str, str]]:
    """Build multi-strategy plain-text queries from interpreted facet slots."""
    return build_facet_search_queries(interpreted=interpreted)
