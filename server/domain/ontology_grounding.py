"""Ontology grounding helpers for dataset discovery search and evidence."""

from __future__ import annotations

from .dataset_search import ConceptMapping, InterpretedQuery
from .ontology_grounder import OntologyGrounder
from .synonym_classification import (
    GEO_REPOSITORY,
    ensure_aliases,
    retrieval_terms_for_mapping,
)

from .facet_search_strategies import FACET_SEARCH_STRATEGIES as GEO_SEARCH_STRATEGIES
from .facet_search_strategies import STRATEGY_PRIORITY

_default_grounder = OntologyGrounder()


def ground_term(slot: str, term: str, top_k: int = 5) -> list[ConceptMapping]:
    """Ground one facet term to ranked ontology concept candidates."""
    return _default_grounder.ground(slot, term, top_k=top_k)


def ground_interpreted_query(interpreted: InterpretedQuery) -> list[ConceptMapping]:
    """Map interpreted query slots to the best grounded ontology concept per slot."""
    return _default_grounder.ground_interpreted_query(interpreted)


def enrich_concept_mappings(
    mappings: list[ConceptMapping],
    *,
    repository: str = GEO_REPOSITORY,
) -> list[ConceptMapping]:
    """Attach classified synonym metadata to grounded concepts."""
    return [ensure_aliases(mapping, repository=repository) for mapping in mappings]


def search_terms_for_mapping(
    mapping: ConceptMapping,
    *,
    repository: str = GEO_REPOSITORY,
) -> list[str]:
    """Terms safe for broad repository search (GEO retrieval)."""
    return retrieval_terms_for_mapping(mapping, repository=repository)


def build_geo_search_term(mappings: list[ConceptMapping]) -> str:
    """Build a GEO query from retrieval-safe grounded concept terms."""
    if not mappings:
        return ""

    groups: list[str] = []
    for mapping in mappings:
        terms = retrieval_terms_for_mapping(mapping, repository=GEO_REPOSITORY)
        if not terms:
            continue
        if len(terms) == 1:
            groups.append(f'"{terms[0]}"' if " " in terms[0] else terms[0])
        else:
            quoted = [f'"{term}"' if " " in term else term for term in terms]
            groups.append(f"({' OR '.join(quoted)})")

    return " AND ".join(groups)


def build_geo_search_queries(
    mappings: list[ConceptMapping],
) -> list[tuple[str, str]]:
    """Build multi-strategy GEO queries from grounded concepts."""
    by_slot = {mapping.slot: mapping for mapping in mappings}
    queries: list[tuple[str, str]] = []

    for strategy, slots in GEO_SEARCH_STRATEGIES:
        subset = [by_slot[slot] for slot in slots if slot in by_slot]
        if not subset:
            continue
        search_term = build_geo_search_term(subset)
        if search_term:
            queries.append((strategy, search_term))

    return queries
