"""Optional LLM-assisted facet extraction for dataset discovery queries."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from anthropic import Anthropic

from domain.dataset_search import InterpretedQuery
from domain.facet_abbreviation_resolution import (
    ACCEPTABLE_MATCH_TYPES,
    MIN_ABBREV_CONFIDENCE,
    QUERY_STOPWORDS,
    mapping_matches_slot,
)
from domain.ontology_grounder import STRONG_MATCH_CONFIDENCE
from domain.ontology_providers.base import is_primary_tier_match
from domain.ontology_grounding import ground_term

logger = logging.getLogger(__name__)

CLAUDE_MODEL = os.getenv("ONTOLOGY_CLAUDE_MODEL", "claude-3-5-haiku-20241022")
INTERPRET_SLOTS = ("disease", "tissue", "assay", "organism")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")


def is_llm_interpret_enabled() -> bool:
    if os.getenv("SCIAGENT_LLM_INTERPRET", "true").strip().lower() in {"0", "false", "no"}:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def should_run_llm_interpret(query: str, interpreted: InterpretedQuery) -> bool:
    """Run LLM interpret only when key is set and core biomedical slots are missing."""
    if not is_llm_interpret_enabled():
        return False

    missing_core = [
        slot
        for slot in ("disease", "tissue", "assay")
        if not getattr(interpreted, slot)
    ]
    if not missing_core:
        return False

    tokens = {
        token.lower()
        for token in WORD_PATTERN.findall(query)
        if token.lower() not in QUERY_STOPWORDS
    }
    return len(tokens) >= 2


def _validate_llm_slot(slot: str, term: str) -> tuple[str | None, dict[str, Any]]:
    candidates = ground_term(slot, term, top_k=3)
    for mapping in candidates:
        if mapping.confidence < MIN_ABBREV_CONFIDENCE:
            continue
        if mapping.match_type not in ACCEPTABLE_MATCH_TYPES:
            continue
        if not mapping_matches_slot(mapping, slot):
            continue
        if slot in {"disease", "assay"} and not is_primary_tier_match(slot, mapping):
            if mapping.confidence < STRONG_MATCH_CONFIDENCE:
                continue
        return mapping.label, {
            "term": term,
            "label": mapping.label,
            "curie": mapping.curie,
            "match_type": mapping.match_type,
            "confidence": mapping.confidence,
            "source": mapping.source,
        }
    return None, {"term": term, "status": "rejected", "reason": "no acceptable ontology match"}


def _extract_llm_facets(query: str) -> dict[str, str | None]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {}

    prompt = (
        "Extract biomedical dataset search facets from the user query. "
        "Return ONLY JSON with keys disease, tissue, assay, organism. "
        "Use null for unknown slots. Prefer concise canonical biomedical terms "
        "(e.g. asthma, PBMC, Flow Cytometry, human).\n\n"
        f"Query: {query}\n"
    )

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            temperature=0.0,
            system=(
                "You extract structured biomedical facets for public dataset discovery. "
                "Respond with valid JSON only."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        payload = json.loads(raw)
    except Exception as exc:
        logger.warning("LLM query interpretation failed: %s", exc)
        return {}

    if not isinstance(payload, dict):
        return {}

    extracted: dict[str, str | None] = {}
    for slot in INTERPRET_SLOTS:
        value = payload.get(slot)
        if value is None or str(value).strip().lower() in {"", "null", "none", "unknown"}:
            extracted[slot] = None
        else:
            extracted[slot] = str(value).strip()
    return extracted


def maybe_llm_interpret_query(
    query: str,
    interpreted: InterpretedQuery,
) -> tuple[InterpretedQuery, dict[str, Any] | None]:
    """
    Fill missing facet slots using an optional LLM pass validated via ontology grounding.

    Returns (merged InterpretedQuery, trace payload or None when skipped).
    """
    if not should_run_llm_interpret(query, interpreted):
        return interpreted, None

    trace: dict[str, Any] = {
        "status": "completed",
        "enabled": True,
        "missing_before": {
            slot: getattr(interpreted, slot)
            for slot in INTERPRET_SLOTS
            if not getattr(interpreted, slot)
        },
        "proposed": {},
        "validated": {},
        "rejected": {},
        "filled_slots": [],
    }

    proposed = _extract_llm_facets(query)
    trace["proposed"] = proposed
    if not proposed:
        trace["status"] = "error"
        trace["error"] = "LLM returned no facet payload"
        return interpreted, trace

    updates: dict[str, str] = {}
    for slot in INTERPRET_SLOTS:
        if getattr(interpreted, slot):
            continue
        term = proposed.get(slot)
        if not term:
            continue
        validated_label, validation_meta = _validate_llm_slot(slot, term)
        if validated_label:
            updates[slot] = validated_label
            trace["validated"][slot] = validation_meta
            trace["filled_slots"].append(slot)
        else:
            trace["rejected"][slot] = validation_meta

    if not updates:
        trace["status"] = "no_validated_slots"
        return interpreted, trace

    merged = interpreted.model_copy(update=updates)

    trace["interpreted_query"] = merged.model_dump()
    return merged, trace
