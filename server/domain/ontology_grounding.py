"""Ontology grounding helpers for dataset discovery search and evidence."""

from __future__ import annotations

from .dataset_search import ConceptMapping, InterpretedQuery
from .ontology_grounder import OntologyGrounder

_default_grounder = OntologyGrounder()

GEO_SEARCH_STRATEGIES: tuple[tuple[str, tuple[str, ...]], ...] = (
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


def ground_term(slot: str, term: str, top_k: int = 5) -> list[ConceptMapping]:
    """Ground one facet term to ranked ontology concept candidates."""
    return _default_grounder.ground(slot, term, top_k=top_k)


def ground_interpreted_query(interpreted: InterpretedQuery) -> list[ConceptMapping]:
    """Map interpreted query slots to the best grounded ontology concept per slot."""
    return _default_grounder.ground_interpreted_query(interpreted)


def search_terms_for_mapping(mapping: ConceptMapping) -> list[str]:
    """All terms to use when searching repositories for a grounded concept."""
    terms = {mapping.label.lower(), mapping.query_term.lower()}
    terms.update(s.lower() for s in mapping.synonyms)

    from .ontology_providers.curated import SEED_CONCEPTS

    seed = SEED_CONCEPTS.get(mapping.query_term) or SEED_CONCEPTS.get(mapping.query_term.lower())
    if seed and seed.get("slot") == mapping.slot:
        terms.update(s.lower() for s in seed.get("synonyms", []))

    return sorted(terms)


def build_geo_search_term(mappings: list[ConceptMapping]) -> str:
    """Build a GEO query from grounded concept synonym groups."""
    if not mappings:
        return ""

    groups: list[str] = []
    for mapping in mappings:
        terms = search_terms_for_mapping(mapping)
        if len(terms) == 1:
            groups.append(f'"{terms[0]}"')
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
