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

            candidates.append(
                ConceptMapping(
                    slot=slot,
                    query_term=term,
                    curie=curie,
                    label=doc.get("label", ""),
                    ontology=str(doc.get("ontology_name", "")).upper(),
                    iri=doc.get("iri"),
                    synonyms=_extract_ols_synonyms(doc),
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


def _extract_ols_synonyms(doc: dict[str, Any]) -> list[str]:
    synonyms: list[str] = []
    for field in ("exact_synonyms", "broad_synonyms", "related_synonyms", "synonyms"):
        values = doc.get(field) or []
        if isinstance(values, list):
            synonyms.extend(str(value) for value in values if value)
    label = doc.get("label")
    if label:
        synonyms.append(str(label))
    return sorted(set(synonyms))
