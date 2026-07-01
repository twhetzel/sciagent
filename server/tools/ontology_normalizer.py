"""
Ontology normalization — maps text terms from tool results to formal ontology terms.

Three-tier lookup: OLS → BioPortal → AI synonym expansion (Claude) + OLS retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import requests
from anthropic import Anthropic

logger = logging.getLogger(__name__)

OLS_BASE_URL = "https://www.ebi.ac.uk/ols4/api"
OLS_ONTOLOGIES = "mondo,hp,go,ncbitaxon,chebi,uberon"
BIOPORTAL_BASE_URL = "https://data.bioontology.org"
REQUEST_TIMEOUT = 15
CACHE_SIZE = 1000
CLAUDE_MODEL = os.getenv("ONTOLOGY_CLAUDE_MODEL", "claude-3-5-haiku-20241022")
MAX_AI_SYNONYMS = 5

_GENE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_SKIP_VALUES = {
    "unknown",
    "n/a",
    "na",
    "none",
    "no summary available",
    "not available",
    "pathogenic",
    "likely pathogenic",
    "benign",
    "likely benign",
    "uncertain significance",
    "conflicting interpretations of pathogenicity",
}


class _LRUCache:
    """Simple in-memory LRU cache for normalization results."""

    def __init__(self, maxsize: int = CACHE_SIZE) -> None:
        self.maxsize = maxsize
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key].copy()

    def set(self, key: str, value: Dict[str, Any]) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value.copy()
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)


_cache = _LRUCache()


def normalize_tool_results(
    results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Normalize ontology-relevant terms in tool results.

    Never raises — returns original results on failure.
    """
    try:
        return asyncio.run(_normalize_tool_results_async(results))
    except Exception as exc:
        logger.exception("Ontology normalization failed: %s", exc)
        return results, {
            "status": "error",
            "error": str(exc),
            "mappings": [],
            "total_terms": 0,
            "matched": 0,
            "unmatched": 0,
        }


def extract_terms_from_result(result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract {text, context} pairs from a single tool result."""
    tool = result.get("tool", "unknown")
    if result.get("status") != "success":
        return []

    data = result.get("data")
    if not isinstance(data, dict):
        return []

    terms: List[Dict[str, str]] = []
    ctx = lambda field: f"{tool}.{field}"

    if tool == "mygene" and data.get("found"):
        _add_term(terms, data.get("name"), ctx("name"))
        _add_term(terms, data.get("type"), ctx("type"))
        for category, go_list in (data.get("go_terms") or {}).items():
            for go_term in go_list or []:
                _add_term(terms, go_term, ctx(f"go.{category}"))
        for pathway in data.get("pathways") or []:
            _add_term(terms, pathway.get("name"), ctx("pathway"))

    elif tool == "uniprot" and data.get("found"):
        _add_term(terms, data.get("protein_name"), ctx("protein_name"))
        organism = data.get("organism") or {}
        _add_term(terms, organism.get("scientific_name"), ctx("organism"))
        for go_entry in data.get("go_terms") or []:
            _add_term(terms, go_entry.get("term"), ctx("go"))

    elif tool == "clinvar":
        _add_term(terms, data.get("gene"), ctx("gene"))
        _add_term(terms, data.get("condition"), ctx("condition"))
        for variant in data.get("variants") or []:
            _add_term(terms, variant.get("condition"), ctx("variant.condition"))
            _add_term(terms, variant.get("clinical_significance"), ctx("variant.clinical_significance"))

    elif tool in ("pubmed", "openalex", "europepmc"):
        for article in data.get("results") or []:
            for mesh in article.get("mesh_terms") or []:
                _add_term(terms, mesh, ctx("mesh"))
            for keyword in article.get("keywords") or []:
                _add_term(terms, keyword, ctx("keyword"))

    elif tool == "alphafold" and data.get("found"):
        _add_term(terms, data.get("protein_name"), ctx("protein_name"))
        _add_term(terms, data.get("organism"), ctx("organism"))
        _add_term(terms, data.get("gene"), ctx("gene"))

    return _dedupe_terms(terms)


def _add_term(terms: List[Dict[str, str]], text: Any, context: str) -> None:
    if not isinstance(text, str):
        return
    cleaned = text.strip()
    if not _is_normalizable(cleaned):
        return
    terms.append({"text": cleaned, "context": context})


def _is_normalizable(text: str) -> bool:
    if len(text) < 3:
        return False
    if text.lower() in _SKIP_VALUES:
        return False
    if _GENE_SYMBOL_RE.match(text):
        return False
    if text.isdigit():
        return False
    return True


def _dedupe_terms(terms: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[Tuple[str, str]] = set()
    unique: List[Dict[str, str]] = []
    for term in terms:
        key = (_normalize_text(term["text"]), term["context"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(term)
    return unique


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _cache_key(text: str, context: str) -> str:
    return f"{_normalize_text(text)}|{context}"


def _unmatched(text: str, context: str) -> Dict[str, Any]:
    return {
        "text": text,
        "context": context,
        "curie": None,
        "label": None,
        "ontology": None,
        "match_type": "unmatched",
        "tier": None,
        "expanded_from": None,
    }


def _format_match(
    text: str,
    context: str,
    curie: str,
    label: str,
    ontology: str,
    match_type: str,
    tier: int,
    expanded_from: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "text": text,
        "context": context,
        "curie": curie,
        "label": label,
        "ontology": ontology,
        "match_type": match_type,
        "tier": tier,
        "expanded_from": expanded_from,
    }


async def _normalize_tool_results_async(
    results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    terms_by_index: Dict[int, List[Dict[str, str]]] = {}
    unique_terms: Dict[Tuple[str, str], Dict[str, str]] = {}

    for idx, result in enumerate(results):
        terms = extract_terms_from_result(result)
        if terms:
            terms_by_index[idx] = terms
            for term in terms:
                key = (_normalize_text(term["text"]), term["context"])
                unique_terms.setdefault(key, term)

    if not unique_terms:
        trace = {
            "status": "skipped",
            "total_terms": 0,
            "matched": 0,
            "unmatched": 0,
            "mappings": [],
        }
        return results, trace

    lookup_tasks = [
        _normalize_term(term["text"], term["context"])
        for term in unique_terms.values()
    ]
    lookup_results = await asyncio.gather(*lookup_tasks, return_exceptions=True)

    normalized_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for term, outcome in zip(unique_terms.values(), lookup_results):
        key = (_normalize_text(term["text"]), term["context"])
        if isinstance(outcome, Exception):
            logger.warning(
                "Normalization failed for %r (%s): %s",
                term["text"],
                term["context"],
                outcome,
            )
            normalized_by_key[key] = _unmatched(term["text"], term["context"])
        else:
            normalized_by_key[key] = outcome

    all_mappings: List[Dict[str, Any]] = []
    updated_results = [dict(result) for result in results]

    for idx, terms in terms_by_index.items():
        normalized_terms: List[Dict[str, Any]] = []
        for term in terms:
            key = (_normalize_text(term["text"]), term["context"])
            mapping = normalized_by_key[key]
            normalized_terms.append(mapping)
            all_mappings.append(
                {
                    **mapping,
                    "source_tool": updated_results[idx].get("tool"),
                }
            )
        updated_results[idx]["normalized_terms"] = normalized_terms

    matched = sum(1 for m in all_mappings if m.get("match_type") != "unmatched")
    trace = {
        "status": "completed",
        "total_terms": len(all_mappings),
        "matched": matched,
        "unmatched": len(all_mappings) - matched,
        "mappings": all_mappings,
    }
    return updated_results, trace


async def _normalize_term(text: str, context: str) -> Dict[str, Any]:
    cached = _cache.get(_cache_key(text, context))
    if cached:
        return cached

    ols_match = await asyncio.to_thread(_lookup_ols, text)
    if ols_match:
        result = _format_match(text, context, **ols_match, tier=1)
        _cache.set(_cache_key(text, context), result)
        return result

    bioportal_match = await asyncio.to_thread(_lookup_bioportal, text)
    if bioportal_match:
        result = _format_match(text, context, **bioportal_match, tier=2)
        _cache.set(_cache_key(text, context), result)
        return result

    ai_match = await _lookup_with_ai_expansion(text, context)
    if ai_match:
        _cache.set(_cache_key(text, context), ai_match)
        return ai_match

    result = _unmatched(text, context)
    _cache.set(_cache_key(text, context), result)
    return result


async def _lookup_with_ai_expansion(text: str, context: str) -> Optional[Dict[str, Any]]:
    synonyms = await asyncio.to_thread(_generate_synonyms, text, context)
    for synonym in synonyms:
        if _normalize_text(synonym) == _normalize_text(text):
            continue
        ols_match = await asyncio.to_thread(_lookup_ols, synonym)
        if ols_match:
            return _format_match(
                text,
                context,
                curie=ols_match["curie"],
                label=ols_match["label"],
                ontology=ols_match["ontology"],
                match_type="ai_expanded_synonym",
                tier=3,
                expanded_from=synonym,
            )
    return None


def _lookup_ols(term: str) -> Optional[Dict[str, str]]:
    try:
        response = requests.get(
            f"{OLS_BASE_URL}/search",
            params={
                "q": term,
                "ontology": OLS_ONTOLOGIES,
                "rows": 10,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
    except requests.RequestException as exc:
        logger.warning("OLS lookup failed for %r: %s", term, exc)
        return None

    for doc in docs:
        match_type = _match_ols_doc(term, doc)
        if match_type:
            return {
                "curie": doc.get("obo_id") or doc.get("short_form", ""),
                "label": doc.get("label", ""),
                "ontology": doc.get("ontology_name", ""),
                "match_type": match_type,
            }
    return None


def _match_ols_doc(term: str, doc: Dict[str, Any]) -> Optional[str]:
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


def _lookup_bioportal(term: str) -> Optional[Dict[str, str]]:
    api_key = os.getenv("BIOPORTAL_API_KEY")
    if not api_key:
        return None

    try:
        response = requests.get(
            f"{BIOPORTAL_BASE_URL}/search",
            params={"q": term, "pagesize": 10},
            headers={"Authorization": f"apikey token={api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        collection = response.json().get("collection", [])
    except requests.RequestException as exc:
        logger.warning("BioPortal lookup failed for %r: %s", term, exc)
        return None

    for item in collection:
        match_type = _match_bioportal_item(term, item)
        if match_type:
            curie = _extract_bioportal_curie(item)
            ontology = _extract_bioportal_ontology(item)
            return {
                "curie": curie,
                "label": item.get("prefLabel", ""),
                "ontology": ontology,
                "match_type": match_type,
            }
    return None


def _match_bioportal_item(term: str, item: Dict[str, Any]) -> Optional[str]:
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


def _extract_bioportal_curie(item: Dict[str, Any]) -> str:
    obo_match = re.search(r"(MONDO|HP|GO|NCBITaxon|CHEBI|UBERON)_\d+", item.get("@id", ""))
    if obo_match:
        prefix, number = obo_match.group(0).split("_", 1)
        if prefix == "NCBITaxon":
            return f"NCBITaxon:{number}"
        return f"{prefix}:{number}"

    notation = item.get("notation")
    if isinstance(notation, str) and notation:
        return notation

    return item.get("@id", "")


def _extract_bioportal_ontology(item: Dict[str, Any]) -> str:
    links = item.get("links") or {}
    ontology_link = links.get("ontology", "")
    if isinstance(ontology_link, str) and ontology_link:
        return ontology_link.rstrip("/").split("/")[-1].lower()
    return ""


def _generate_synonyms(text: str, context: str) -> List[str]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    prompt = (
        "Generate up to {max_synonyms} alternative biomedical ontology search terms "
        "for normalizing the following text to a formal ontology term (MONDO, HP, GO, "
        "NCBITaxon, CHEBI, UBERON). Return ONLY a JSON array of strings.\n\n"
        "Original text: {text}\n"
        "Source context: {context}\n"
    ).format(max_synonyms=MAX_AI_SYNONYMS, text=text, context=context)

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            temperature=0.2,
            system=(
                "You expand biomedical terms into ontology-friendly synonyms. "
                "Respond with valid JSON only."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        synonyms = json.loads(raw)
        if isinstance(synonyms, list):
            return [s for s in synonyms if isinstance(s, str) and s.strip()][:MAX_AI_SYNONYMS]
    except Exception as exc:
        logger.warning("AI synonym expansion failed for %r: %s", text, exc)
    return []
