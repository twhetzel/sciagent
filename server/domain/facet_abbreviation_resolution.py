"""Resolve abbreviated facet tokens during query interpretation."""

from __future__ import annotations

import re

from .dataset_search import ConceptMapping, InterpretedQuery
from .facet_query_normalization import extract_parenthetical_abbrevs, normalize_unicode_text
from .ontology_providers.obo_foundry_policy import SLOT_CURIE_PREFIXES
from .ontology_grounding import ground_term
from .ontology_providers.curated import CuratedAliasProvider
from .synonym_classification import (
    BLOCKED_SHORT_ACRONYMS,
    _is_acronym_like,
    _normalize_text,
    ensure_aliases,
    has_acronym_context,
)

TOKEN_PATTERN = re.compile(r"\b([A-Za-z]{2,4})\b")

QUERY_STOPWORDS = frozenset(
    {
        "and",
        "are",
        "at",
        "collected",
        "data",
        "dataset",
        "datasets",
        "find",
        "for",
        "from",
        "geo",
        "gse",
        "in",
        "of",
        "or",
        "public",
        "the",
        "with",
        "your",
    }
)

ASSAY_QUERY_WORDS = frozenset(
    {
        "microarray",
        "profiling",
        "rna",
        "rnaseq",
        "seq",
        "sequencing",
        "transcriptome",
    }
)

MAX_DYNAMIC_GROUNDING_ATTEMPTS = 6

SLOT_FILL_ORDER = ("disease", "tissue", "assay", "organism")

ACCEPTABLE_MATCH_TYPES = frozenset(
    {
        "curated_exact",
        "curated_synonym",
        "exact",
        "synonym",
    }
)

MIN_ABBREV_CONFIDENCE = 0.74

_curated_provider = CuratedAliasProvider()


def mapping_matches_slot(mapping: ConceptMapping, slot: str) -> bool:
    """Return whether a grounded concept belongs to the expected facet slot."""
    prefixes = SLOT_CURIE_PREFIXES.get(slot)
    if not prefixes:
        return True
    curie = mapping.curie.upper()
    return any(curie.startswith(prefix.upper()) for prefix in prefixes)


def curated_facet_lookup(slot: str, term: str) -> list[ConceptMapping]:
    return _curated_provider.lookup(slot, term)


def ground_facet_candidate(
    slot: str,
    token: str,
    *,
    allow_dynamic: bool = True,
) -> list[ConceptMapping]:
    """Prefer local curated aliases before dynamic ontology lookup."""
    curated = _curated_provider.lookup(slot, token)
    if curated:
        return curated[:1]
    if allow_dynamic:
        return ground_term(slot, token, top_k=1)
    return []


def ground_phrase_variants(
    slot: str,
    phrase: str,
    *,
    allow_dynamic: bool,
) -> tuple[list[ConceptMapping], bool]:
    """
    Try curated and dynamic grounding across punctuation-normalized phrase variants.

    Returns (candidates, used_dynamic_attempt). The attempt flag is True only when
    dynamic lookup returned at least one candidate (empty OLS/BioPortal responses
    do not consume the phrase-resolution attempt budget).
    """
    from .facet_query_normalization import grounding_phrase_variants

    variants = grounding_phrase_variants(phrase)
    for variant in variants:
        curated = curated_facet_lookup(slot, variant)
        if curated:
            return curated[:1], False

    if allow_dynamic:
        for variant in variants:
            results = ground_term(slot, variant, top_k=1)
            if results:
                return results, True
        return [], False

    return [], False


def _ground_abbreviation(slot: str, token: str) -> list[ConceptMapping]:
    return ground_facet_candidate(slot, token)


def _facet_terms(interpreted: InterpretedQuery) -> set[str]:
    terms: set[str] = set()
    for slot in SLOT_FILL_ORDER:
        value = getattr(interpreted, slot)
        if value:
            terms.add(_normalize_text(value))
    return terms


def _abbreviation_candidates(query: str, interpreted: InterpretedQuery) -> list[str]:
    """Return abbreviation-like tokens from the query that are not already facet values."""
    facet_terms = _facet_terms(interpreted)
    seen: set[str] = set()
    candidates: list[str] = []

    def add(token: str) -> None:
        normalized = _normalize_text(token)
        if normalized in seen or normalized in facet_terms or normalized in QUERY_STOPWORDS:
            return
        if normalized in BLOCKED_SHORT_ACRONYMS or _is_acronym_like(token):
            seen.add(normalized)
            candidates.append(token)

    normalized_query = normalize_unicode_text(query)
    for token in extract_parenthetical_abbrevs(normalized_query):
        add(token)

    for match in TOKEN_PATTERN.finditer(normalized_query):
        add(match.group(1))

    return candidates


def _accept_abbreviation_grounding(
    mapping: ConceptMapping,
    *,
    query: str,
    token: str,
    slot: str,
) -> bool:
    if mapping.confidence < MIN_ABBREV_CONFIDENCE:
        return False
    if mapping.match_type not in ACCEPTABLE_MATCH_TYPES:
        return False
    if not mapping_matches_slot(mapping, slot):
        return False

    normalized = _normalize_text(token)
    if normalized in BLOCKED_SHORT_ACRONYMS or _is_acronym_like(token):
        return has_acronym_context(query, ensure_aliases(mapping))
    return True


def resolve_abbreviated_facets(query: str, interpreted: InterpretedQuery) -> InterpretedQuery:
    """
    Fill empty facet slots by grounding abbreviation-like tokens from the query.

    Abbreviations are resolved to ontology concepts for search planning, but unsafe
    short forms remain excluded from GEO retrieval via synonym classification.
    """
    updates: dict[str, str] = {}
    consumed_tokens: set[str] = set()

    for slot in SLOT_FILL_ORDER:
        if getattr(interpreted, slot):
            continue

        for token in _abbreviation_candidates(query, interpreted):
            normalized = _normalize_text(token)
            if normalized in consumed_tokens:
                continue

            candidates = _ground_abbreviation(slot, token)
            if not candidates:
                continue

            mapping = candidates[0]
            if not _accept_abbreviation_grounding(mapping, query=query, token=token, slot=slot):
                continue

            updates[slot] = token
            consumed_tokens.add(normalized)
            break

    if not updates:
        return interpreted

    return interpreted.model_copy(update=updates)
