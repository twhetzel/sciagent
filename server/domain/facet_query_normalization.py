"""Normalize query text for facet abbreviation and phrase extraction."""

from __future__ import annotations

import re
import unicodedata

from .synonym_classification import BLOCKED_SHORT_ACRONYMS, _is_acronym_like, _normalize_text

# Clause / list delimiters → space (hyphens kept for within-token compounds).
CLAUSE_DELIMITER_PATTERN = re.compile(r"[,;/|]+")

# Parenthetical segments, e.g. (UC), (PD).
PARENTHETICAL_PATTERN = re.compile(r"\(([^)]*)\)")

# Apostrophe possessive → plain form (Parkinson's disease → Parkinson disease).
POSSESSIVE_APOSTROPHE_PATTERN = re.compile(r"'s\b", re.IGNORECASE)

# Hyphen between word characters (ulcerative-colitis → ulcerative colitis for lookup).
INTERNAL_HYPHEN_PATTERN = re.compile(r"(?<=\w)-(?=\w)")

# Curly/smart quotes → ASCII apostrophe.
APOSTROPHE_VARIANTS = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201b": "'",
    "`": "'",
})


def normalize_unicode_text(text: str) -> str:
    """Apply Unicode NFKC normalization and unify apostrophe variants."""
    return unicodedata.normalize("NFKC", text).translate(APOSTROPHE_VARIANTS)


def extract_parenthetical_abbrevs(query: str) -> list[str]:
    """Return acronym-like tokens found inside parentheses."""
    candidates: list[str] = []
    seen: set[str] = set()

    for match in PARENTHETICAL_PATTERN.finditer(query):
        inner = match.group(1).strip()
        if not inner:
            continue
        for token in re.findall(r"[A-Za-z0-9]+", inner):
            normalized = _normalize_text(token)
            if normalized in seen:
                continue
            if normalized in BLOCKED_SHORT_ACRONYMS or _is_acronym_like(token):
                seen.add(normalized)
                candidates.append(token)

    return candidates


def strip_parentheticals(text: str) -> str:
    """Remove parenthetical segments so they do not break n-gram extraction."""
    return PARENTHETICAL_PATTERN.sub(" ", text)


def normalize_clause_delimiters(text: str) -> str:
    """Turn list/clause punctuation into word boundaries."""
    return CLAUSE_DELIMITER_PATTERN.sub(" ", text)


def normalize_query_for_phrases(query: str) -> str:
    """
    Produce a punctuation-normalized query string for phrase n-gram scanning.

    Parenthetical abbreviations are stripped (and should be handled separately).
    Commas, semicolons, and slashes become spaces; smart quotes are unified.
    """
    text = normalize_unicode_text(query)
    text = strip_parentheticals(text)
    text = normalize_clause_delimiters(text)
    return re.sub(r"\s+", " ", text).strip()


def grounding_phrase_variants(phrase: str) -> list[str]:
    """
    Return phrase variants to try during ontology grounding.

    Hyphenated compounds also try a spaced form (ulcerative-colitis → ulcerative colitis).
    """
    cleaned = re.sub(r"\s+", " ", phrase.strip())
    if not cleaned:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        variants.append(value.strip())

    add(cleaned)
    add(strip_parentheticals(cleaned))
    add(INTERNAL_HYPHEN_PATTERN.sub(" ", cleaned))
    add(INTERNAL_HYPHEN_PATTERN.sub(" ", strip_parentheticals(cleaned)))
    add(POSSESSIVE_APOSTROPHE_PATTERN.sub("", cleaned))
    add(POSSESSIVE_APOSTROPHE_PATTERN.sub("s", cleaned))
    add(INTERNAL_HYPHEN_PATTERN.sub(" ", POSSESSIVE_APOSTROPHE_PATTERN.sub("", cleaned)))

    return variants
