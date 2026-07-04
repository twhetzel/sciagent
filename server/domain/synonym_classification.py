"""Classify ontology synonyms for safe GEO retrieval vs contextual evidence."""

from __future__ import annotations

import re

from .dataset_search import ConceptMapping, SynonymAlias

GEO_REPOSITORY = "GEO"
MIN_SAFE_SINGLE_WORD_LENGTH = 4

BLOCKED_SHORT_ACRONYMS: frozenset[str] = frozenset({"uc", "cd", "ad", "pd", "ms"})

RETRIEVAL_WHITELIST: dict[str, dict[str, frozenset[str]]] = {
    GEO_REPOSITORY: {
        "disease": frozenset(),
        "tissue": frozenset(),
        "assay": frozenset(),
        "organism": frozenset(),
    },
}

DISEASE_ACRONYM_CONTEXT_TERMS: tuple[str, ...] = (
    "colitis",
    "inflammatory bowel disease",
    "ibd",
    "colon",
    "colonic",
    "mucosa",
    "patient",
    "patients",
    "disease",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _is_acronym_like(term: str) -> bool:
    stripped = term.strip()
    if not stripped or " " in stripped:
        return False
    alpha = re.sub(r"[^a-zA-Z]", "", stripped)
    if not alpha:
        return False
    if len(alpha) <= 3:
        return True
    return alpha.isupper() and len(alpha) <= 4


def _category_from_ontology_scope(scope: str, term: str, label: str) -> str:
    """Map provider synonym scope to alias category."""
    if scope == "label":
        return "preferred_label"
    if scope == "exact":
        return "exact_synonym"
    if scope == "dataset":
        return "dataset_phrase"
    if scope == "broad":
        return "broad_synonym"
    if scope == "related":
        return "related_synonym"
    return _category_for_term(term, label)


def _category_for_term(term: str, label: str) -> str:
    norm_term = _normalize_text(term)
    norm_label = _normalize_text(label)
    if norm_term == norm_label:
        return "preferred_label"
    if " " in term.strip():
        return "exact_synonym"
    if norm_term in BLOCKED_SHORT_ACRONYMS or _is_acronym_like(term):
        return "acronym" if term.strip().isupper() or len(norm_term) <= 3 else "abbreviation"
    if len(norm_term) >= MIN_SAFE_SINGLE_WORD_LENGTH:
        return "exact_synonym"
    return "abbreviation"


def _is_whitelisted(term: str, slot: str, repository: str) -> bool:
    norm = _normalize_text(term)
    return norm in RETRIEVAL_WHITELIST.get(repository, {}).get(slot, frozenset())


def _safe_for_retrieval(
    term: str,
    category: str,
    slot: str,
    repository: str,
) -> bool:
    if category in {"broad_synonym", "related_synonym"}:
        return False

    norm = _normalize_text(term)
    if category == "preferred_label":
        return True
    if _is_whitelisted(term, slot, repository):
        return True
    if category in {"exact_synonym", "dataset_phrase"}:
        if " " in term.strip():
            return True
        if norm in BLOCKED_SHORT_ACRONYMS:
            return False
        if _is_acronym_like(term):
            return False
        return len(norm) >= MIN_SAFE_SINGLE_WORD_LENGTH
    if " " in term.strip():
        return True
    if norm in BLOCKED_SHORT_ACRONYMS:
        return False
    if category in {"acronym", "abbreviation"}:
        return False
    if _is_acronym_like(term):
        return False
    return len(norm) >= MIN_SAFE_SINGLE_WORD_LENGTH


def classify_term(
    term: str,
    *,
    label: str,
    source: str,
    slot: str,
    repository: str = GEO_REPOSITORY,
    ontology_scope: str | None = None,
) -> SynonymAlias:
    """Assign retrieval/evidence metadata to one synonym or alias."""
    if ontology_scope:
        category = _category_from_ontology_scope(ontology_scope, term, label)
    else:
        category = _category_for_term(term, label)
    safe = _safe_for_retrieval(term, category, slot, repository)
    requires_context = not safe and (
        category in {"acronym", "abbreviation"} or _is_acronym_like(term)
    )
    return SynonymAlias(
        term=term,
        source=source,
        category=category,
        safe_for_retrieval=safe,
        requires_context=requires_context,
    )


def _seed_synonyms_for_mapping(mapping: ConceptMapping) -> list[str]:
    from .ontology_providers.curated import SEED_CONCEPTS

    seed = SEED_CONCEPTS.get(mapping.query_term) or SEED_CONCEPTS.get(
        _normalize_text(mapping.query_term)
    )
    if seed and seed.get("slot") == mapping.slot:
        return list(seed.get("synonyms", []))
    return []


def build_aliases_for_mapping(
    mapping: ConceptMapping,
    *,
    repository: str = GEO_REPOSITORY,
) -> list[SynonymAlias]:
    """Build synonym metadata for one grounded concept."""
    seen: set[str] = set()
    aliases: list[SynonymAlias] = []

    def add(term: str, source: str, *, ontology_scope: str | None = None) -> None:
        cleaned = term.strip()
        if not cleaned:
            return
        key = _normalize_text(cleaned)
        if key in seen:
            return
        seen.add(key)
        scope = ontology_scope or (mapping.synonym_scopes or {}).get(key)
        aliases.append(
            classify_term(
                cleaned,
                label=mapping.label,
                source=source,
                slot=mapping.slot,
                repository=repository,
                ontology_scope=scope,
            )
        )

    add(mapping.label, mapping.source, ontology_scope="label")
    add(mapping.query_term, "query", ontology_scope="exact")
    for synonym in mapping.synonyms:
        add(synonym, mapping.source)
    for synonym in _seed_synonyms_for_mapping(mapping):
        add(synonym, "curated", ontology_scope="dataset")

    return aliases


def ensure_aliases(
    mapping: ConceptMapping,
    *,
    repository: str = GEO_REPOSITORY,
) -> ConceptMapping:
    """Return a mapping with populated alias metadata."""
    if mapping.aliases:
        return mapping
    return mapping.model_copy(
        update={"aliases": build_aliases_for_mapping(mapping, repository=repository)}
    )


def retrieval_terms_for_mapping(
    mapping: ConceptMapping,
    *,
    repository: str = GEO_REPOSITORY,
) -> list[str]:
    """Terms safe for broad repository search."""
    enriched = ensure_aliases(mapping, repository=repository)
    return sorted(
        {_normalize_text(alias.term) for alias in enriched.aliases if alias.safe_for_retrieval}
    )


def evidence_terms_for_mapping(
    mapping: ConceptMapping,
    *,
    repository: str = GEO_REPOSITORY,
) -> list[str]:
    """Terms that may match directly in metadata without contextual acronym rules."""
    enriched = ensure_aliases(mapping, repository=repository)
    return sorted(
        {
            _normalize_text(alias.term)
            for alias in enriched.aliases
            if alias.safe_for_retrieval
            or alias.category in {"broad_synonym", "related_synonym"}
            or (not alias.requires_context and alias.category not in {"acronym", "abbreviation"})
        }
    )


def contextual_acronyms_for_mapping(
    mapping: ConceptMapping,
    *,
    repository: str = GEO_REPOSITORY,
) -> list[SynonymAlias]:
    """Short aliases that require nearby supporting text for evidence."""
    enriched = ensure_aliases(mapping, repository=repository)
    return [alias for alias in enriched.aliases if alias.requires_context]


def _disease_context_terms(mapping: ConceptMapping) -> list[str]:
    terms = list(DISEASE_ACRONYM_CONTEXT_TERMS)
    for alias in mapping.aliases:
        if alias.safe_for_retrieval:
            terms.append(alias.term)
    if mapping.label:
        terms.append(mapping.label)
    return sorted({_normalize_text(term) for term in terms if term.strip()})


def _generic_context_terms(mapping: ConceptMapping) -> list[str]:
    terms: list[str] = []
    if mapping.label:
        terms.append(mapping.label)
    for alias in mapping.aliases:
        if alias.safe_for_retrieval:
            terms.append(alias.term)
    return sorted({_normalize_text(term) for term in terms if term.strip()})


def context_terms_for_mapping(mapping: ConceptMapping) -> list[str]:
    """Supporting terms that must appear near a contextual acronym."""
    enriched = ensure_aliases(mapping)
    if enriched.slot == "disease":
        return _disease_context_terms(enriched)
    return _generic_context_terms(enriched)


def term_in_text(term: str, text: str) -> bool:
    """Case-insensitive whole-term match, substring match for multi-word terms."""
    normalized_term = _normalize_text(term)
    normalized_text = _normalize_text(text)
    if not normalized_term or not normalized_text:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"\b{re.escape(normalized_term)}\b", normalized_text) is not None


def has_acronym_context(text: str, mapping: ConceptMapping) -> bool:
    """Return whether text contains enough context to trust a short acronym."""
    return any(term_in_text(context, text) for context in context_terms_for_mapping(mapping))


def terms_matching_in_text(
    mapping: ConceptMapping,
    text: str,
    *,
    repository: str = GEO_REPOSITORY,
) -> list[str]:
    """Return normalized terms from the mapping that match text."""
    enriched = ensure_aliases(mapping, repository=repository)
    matched: set[str] = set()

    for alias in enriched.aliases:
        if alias.safe_for_retrieval and term_in_text(alias.term, text):
            matched.add(_normalize_text(alias.term))
            continue
        if alias.category in {"broad_synonym", "related_synonym"} and term_in_text(
            alias.term, text
        ):
            matched.add(_normalize_text(alias.term))
            continue
        if alias.requires_context and term_in_text(alias.term, text) and has_acronym_context(
            text, enriched
        ):
            matched.add(_normalize_text(alias.term))

    return sorted(matched)
