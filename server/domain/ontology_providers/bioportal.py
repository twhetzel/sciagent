"""BioPortal-backed ontology grounding provider."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from domain.dataset_search import ConceptMapping

from .base import CONFIDENCE_BY_MATCH, FACET_ONTOLOGIES

logger = logging.getLogger(__name__)

BIOPORTAL_BASE_URL = "https://data.bioontology.org"
REQUEST_TIMEOUT = 15


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class BioPortalProvider:
    """Dynamic ontology lookup via BioPortal when configured."""

    name = "bioportal"

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        api_key = os.getenv("BIOPORTAL_API_KEY")
        if not api_key:
            return []

        ontologies = FACET_ONTOLOGIES.get(slot, [])
        if not ontologies:
            return []

        try:
            response = requests.get(
                f"{BIOPORTAL_BASE_URL}/search",
                params={
                    "q": term,
                    "pagesize": 10,
                    "require_exact_match": "false",
                },
                headers={"Authorization": f"apikey token={api_key}"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            collection = response.json().get("collection", [])
        except requests.RequestException as exc:
            logger.warning("BioPortal lookup failed for %r (%s): %s", term, slot, exc)
            return []

        allowed = {ontology.lower() for ontology in ontologies}
        candidates: list[ConceptMapping] = []
        for item in collection:
            ontology = _extract_bioportal_ontology(item)
            if ontology and ontology not in allowed:
                continue

            match_type = _match_bioportal_item(term, item)
            if not match_type:
                continue

            curie = _extract_bioportal_curie(item)
            if not curie:
                continue

            synonyms, synonym_scopes = _extract_bioportal_synonym_data(item)
            candidates.append(
                ConceptMapping(
                    slot=slot,
                    query_term=term,
                    curie=curie,
                    label=item.get("prefLabel", ""),
                    ontology=ontology.upper() if ontology else "",
                    iri=item.get("@id"),
                    synonyms=synonyms,
                    synonym_scopes=synonym_scopes,
                    match_type=match_type,
                    source=self.name,
                    confidence=CONFIDENCE_BY_MATCH[match_type],
                    explanation=f"BioPortal {match_type} match for {slot}={term}",
                )
            )
        return candidates


def _match_bioportal_item(term: str, item: dict[str, Any]) -> str | None:
    norm_term = _normalize_text(term)
    pref_label = _normalize_text(item.get("prefLabel", ""))
    if norm_term == pref_label:
        return "exact"

    match_type = str(item.get("matchType", "")).lower()
    if match_type == "synonym":
        return "synonym"

    for synonym in item.get("synonym") or []:
        if isinstance(synonym, str) and _normalize_text(synonym) == norm_term:
            return "synonym"
    return None


def _extract_bioportal_curie(item: dict[str, Any]) -> str:
    obo_match = re.search(
        r"(MONDO|DOID|EFO|HP|GO|NCBITaxon|CHEBI|UBERON|OBI)_\d+",
        item.get("@id", ""),
    )
    if obo_match:
        prefix, number = obo_match.group(0).split("_", 1)
        if prefix == "NCBITaxon":
            return f"NCBITaxon:{number}"
        return f"{prefix}:{number}"

    notation = item.get("notation")
    if isinstance(notation, str) and notation:
        return notation
    return item.get("@id", "")


def _extract_bioportal_ontology(item: dict[str, Any]) -> str:
    links = item.get("links") or {}
    ontology_link = links.get("ontology", "")
    if isinstance(ontology_link, str) and ontology_link:
        return ontology_link.rstrip("/").split("/")[-1].lower()
    return ""


def _extract_bioportal_synonym_data(item: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Return synonym strings and scope metadata (BioPortal search is mostly untyped)."""
    scopes: dict[str, str] = {}
    synonyms: list[str] = []

    pref_label = item.get("prefLabel")
    if pref_label:
        label_text = str(pref_label)
        synonyms.append(label_text)
        scopes[_normalize_text(label_text)] = "label"

    for value in item.get("synonym") or []:
        if not value:
            continue
        term = str(value)
        synonyms.append(term)
        scopes.setdefault(_normalize_text(term), "exact")

    return sorted(set(synonyms)), scopes


def _extract_bioportal_synonyms(item: dict[str, Any]) -> list[str]:
    synonyms, _ = _extract_bioportal_synonym_data(item)
    return synonyms
