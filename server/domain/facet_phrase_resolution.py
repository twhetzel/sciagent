"""Resolve multi-word facet phrases during query interpretation via ontology grounding."""

from __future__ import annotations

import re

from .dataset_search import ConceptMapping, InterpretedQuery
from .facet_abbreviation_resolution import (
    ACCEPTABLE_MATCH_TYPES,
    ASSAY_QUERY_WORDS,
    MAX_DYNAMIC_GROUNDING_ATTEMPTS,
    MIN_ABBREV_CONFIDENCE,
    QUERY_STOPWORDS,
    SLOT_FILL_ORDER,
    curated_facet_lookup,
    ground_phrase_variants,
    mapping_matches_slot,
)
from .facet_query_normalization import normalize_query_for_phrases
from .synonym_classification import (
    BLOCKED_SHORT_ACRONYMS,
    _is_acronym_like,
    _normalize_text,
    ensure_aliases,
    has_acronym_context,
)

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")

GENERIC_PHRASES = frozenset(
    {
        "disease",
        "tissue",
        "patient",
        "patients",
        "sample",
        "samples",
        "study",
        "studies",
        "expression",
        "profiling",
        "immune response",
    }
)

MAX_PHRASE_WORDS = 5
MIN_SINGLE_WORD_DYNAMIC_LENGTH = 4
SINGLE_WORD_DYNAMIC_SLOTS = frozenset({"disease", "assay"})


def _filled_facet_values(interpreted: InterpretedQuery) -> set[str]:
    values: set[str] = set()
    for slot in SLOT_FILL_ORDER:
        value = getattr(interpreted, slot)
        if value:
            values.add(_normalize_text(value))
    return values


def _phrase_words(phrase: str) -> set[str]:
    return {_normalize_text(word) for word in WORD_PATTERN.findall(phrase)}


def _phrase_contains_stopword(phrase: str) -> bool:
    """Skip n-grams that mix facet terms with query boilerplate (e.g. datasets for)."""
    return bool(_phrase_words(phrase) & QUERY_STOPWORDS)


def _candidate_phrases(query: str, interpreted: InterpretedQuery) -> list[str]:
    """Return query n-grams longest-first, excluding stopwords and filled facets."""
    normalized_query = normalize_query_for_phrases(query)
    matches = list(WORD_PATTERN.finditer(normalized_query))
    if not matches:
        return []

    filled_values = _filled_facet_values(interpreted)
    seen: set[str] = set()
    phrases: list[str] = []

    for start_index in range(len(matches)):
        for end_index in range(start_index + 1, min(start_index + MAX_PHRASE_WORDS, len(matches)) + 1):
            phrase = normalized_query[matches[start_index].start() : matches[end_index - 1].end()].strip()
            normalized = _normalize_text(phrase)
            if not normalized or normalized in seen:
                continue
            if normalized in QUERY_STOPWORDS or normalized in GENERIC_PHRASES:
                continue
            if _phrase_contains_stopword(phrase):
                continue
            if normalized in filled_values:
                continue
            if "(" in phrase or ")" in phrase:
                continue

            words = _phrase_words(phrase)
            if words.issubset(QUERY_STOPWORDS):
                continue
            first_word = next(iter(WORD_PATTERN.finditer(phrase)), None)
            if first_word and _normalize_text(first_word.group()) in QUERY_STOPWORDS:
                continue
            if interpreted.assay and words & ASSAY_QUERY_WORDS:
                continue
            if len(words) == 1 and (
                _normalize_text(phrase) in BLOCKED_SHORT_ACRONYMS or _is_acronym_like(phrase)
            ):
                continue

            seen.add(normalized)
            phrases.append(phrase)

    return phrases


def _sort_phrases_longest_first(phrases: list[str]) -> list[str]:
    return sorted(phrases, key=lambda item: (-len(_phrase_words(item)), item.lower()))


def _sort_phrases_shortest_first(phrases: list[str]) -> list[str]:
    return sorted(phrases, key=lambda item: (len(_phrase_words(item)), item.lower()))


def _phrase_relevant_for_slot(phrase: str, slot: str) -> bool:
    """Skip composite phrases that likely belong to another facet slot."""
    words = _phrase_words(phrase)
    if slot == "disease" and words & {"tissue", "biopsies", "biopsy", "samples", "seq", "rnaseq"}:
        return False
    if slot == "tissue" and words & {"disease", "syndrome", "disorder"} and len(words) > 2:
        return False
    return True


def _accept_phrase_grounding(
    mapping: ConceptMapping,
    *,
    query: str,
    phrase: str,
    slot: str,
) -> bool:
    if mapping.confidence < MIN_ABBREV_CONFIDENCE:
        return False
    if mapping.match_type not in ACCEPTABLE_MATCH_TYPES:
        return False
    if not mapping_matches_slot(mapping, slot):
        return False

    normalized = _normalize_text(phrase)
    if normalized in BLOCKED_SHORT_ACRONYMS:
        return has_acronym_context(query, ensure_aliases(mapping))
    return True


def resolve_phrase_facets(query: str, interpreted: InterpretedQuery) -> InterpretedQuery:
    """
    Fill empty facet slots by grounding multi-word phrases from the query.

    Runs after regex and abbreviation resolution to catch disease/tissue terms
    that are not covered by fixed patterns (e.g. Crohn's disease, ileum).
    """
    updates: dict[str, str] = {}
    consumed_words: set[str] = set()
    dynamic_attempts = 0
    candidates = _candidate_phrases(query, interpreted)

    def try_fill(*, allow_dynamic: bool, phrase_order: list[str]) -> None:
        nonlocal dynamic_attempts

        for slot in SLOT_FILL_ORDER:
            if getattr(interpreted, slot) or slot in updates:
                continue

            for phrase in phrase_order:
                if _phrase_words(phrase) & consumed_words:
                    continue
                if not _phrase_relevant_for_slot(phrase, slot):
                    continue

                can_use_dynamic = allow_dynamic and dynamic_attempts < MAX_DYNAMIC_GROUNDING_ATTEMPTS
                if not allow_dynamic:
                    can_use_dynamic = False
                elif len(_phrase_words(phrase)) == 1:
                    if slot == "tissue":
                        if not curated_facet_lookup(slot, phrase):
                            continue
                    elif slot in SINGLE_WORD_DYNAMIC_SLOTS:
                        normalized_phrase = _normalize_text(phrase)
                        if len(normalized_phrase) < MIN_SINGLE_WORD_DYNAMIC_LENGTH:
                            continue
                        if normalized_phrase in BLOCKED_SHORT_ACRONYMS or _is_acronym_like(phrase):
                            continue
                    else:
                        continue

                grounded, used_dynamic = ground_phrase_variants(
                    slot,
                    phrase,
                    allow_dynamic=can_use_dynamic,
                )
                if not grounded:
                    continue
                if used_dynamic:
                    dynamic_attempts += 1

                mapping = grounded[0]
                if not _accept_phrase_grounding(mapping, query=query, phrase=phrase, slot=slot):
                    continue

                updates[slot] = mapping.label
                consumed_words.update(_phrase_words(phrase))
                break

    # Prefer specific multi-word phrases before shorter subsets (e.g. peanut allergy before allergy).
    try_fill(allow_dynamic=False, phrase_order=_sort_phrases_longest_first(candidates))
    try_fill(allow_dynamic=True, phrase_order=_sort_phrases_longest_first(candidates))

    if not updates:
        return interpreted

    merged = interpreted.model_copy(update=updates)
    return merged
