"""OLS-backed ontology grounding provider."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from domain.dataset_search import ConceptMapping

from .base import CONFIDENCE_BY_MATCH, FACET_ONTOLOGIES

logger = logging.getLogger(__name__)

OLS_BASE_URL = "https://www.ebi.ac.uk/ols4/api"
REQUEST_TIMEOUT = 15


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class OLSProvider:
    """Dynamic ontology lookup via EBI OLS."""

    name = "ols"

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        ontologies = FACET_ONTOLOGIES.get(slot, [])
        if not ontologies:
            return []

        try:
            response = requests.get(
                f"{OLS_BASE_URL}/search",
                params={
                    "q": term,
                    "ontology": ",".join(ontologies),
                    "rows": 10,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            docs = response.json().get("response", {}).get("docs", [])
        except requests.RequestException as exc:
            logger.warning("OLS lookup failed for %r (%s): %s", term, slot, exc)
            return []

        candidates: list[ConceptMapping] = []
        for doc in docs:
            match_type = _match_ols_doc(term, doc)
            if not match_type:
                continue

            curie = doc.get("obo_id") or doc.get("short_form", "")
            if not curie:
                continue

            synonyms, synonym_scopes = _extract_ols_synonym_data(doc)
            candidates.append(
                ConceptMapping(
                    slot=slot,
                    query_term=term,
                    curie=curie,
                    label=doc.get("label", ""),
                    ontology=str(doc.get("ontology_name", "")).upper(),
                    iri=doc.get("iri"),
                    synonyms=synonyms,
                    synonym_scopes=synonym_scopes,
                    match_type=match_type,
                    source=self.name,
                    confidence=CONFIDENCE_BY_MATCH[match_type],
                    explanation=f"OLS {match_type} match for {slot}={term}",
                )
            )
        return candidates


def _match_ols_doc(term: str, doc: dict[str, Any]) -> str | None:
    norm_term = _normalize_text(term)
    label = _normalize_text(doc.get("label", ""))
    if norm_term == label:
        return "exact"

    for field in ("exact_synonyms", "broad_synonyms", "related_synonyms", "synonyms"):
        synonyms = doc.get(field) or []
        if not isinstance(synonyms, list):
            continue
        for synonym in synonyms:
            if isinstance(synonym, str) and _normalize_text(synonym) == norm_term:
                return "synonym"
    return None


def _extract_ols_synonym_data(doc: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Return all synonym strings and normalized-term → OLS scope metadata."""
    scope_by_field = {
        "exact_synonyms": "exact",
        "broad_synonyms": "broad",
        "related_synonyms": "related",
    }
    scopes: dict[str, str] = {}
    synonyms: list[str] = []

    label = doc.get("label")
    if label:
        label_text = str(label)
        synonyms.append(label_text)
        scopes[_normalize_text(label_text)] = "label"

    for field, scope in scope_by_field.items():
        values = doc.get(field) or []
        if not isinstance(values, list):
            continue
        for value in values:
            if not value:
                continue
            term = str(value)
            synonyms.append(term)
            scopes[_normalize_text(term)] = scope

    legacy_values = doc.get("synonyms") or []
    if isinstance(legacy_values, list):
        for value in legacy_values:
            if not value:
                continue
            term = str(value)
            key = _normalize_text(term)
            synonyms.append(term)
            if key not in scopes:
                scopes[key] = "exact"

    return sorted(set(synonyms)), scopes


def _extract_ols_synonyms(doc: dict[str, Any]) -> list[str]:
    synonyms, _ = _extract_ols_synonym_data(doc)
    return synonyms
