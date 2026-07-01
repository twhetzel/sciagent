"""LLM-assisted alias expansion for ontology grounding (not a source of truth for IDs)."""

from __future__ import annotations

import json
import logging
import os
import re

from anthropic import Anthropic

from domain.dataset_search import ConceptMapping

from .base import CONFIDENCE_BY_MATCH
from .bioportal import BioPortalProvider
from .ols import OLSProvider

logger = logging.getLogger(__name__)

CLAUDE_MODEL = os.getenv("ONTOLOGY_CLAUDE_MODEL", "claude-3-5-haiku-20241022")
MAX_AI_SYNONYMS = 5


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class LLMDisambiguationProvider:
    """
    Suggest alternate search terms with an LLM, then resolve IDs via OLS/BioPortal.

    The LLM never assigns ontology IDs directly.
    """

    name = "llm_disambiguation"

    def __init__(self) -> None:
        self._ols = OLSProvider()
        self._bioportal = BioPortalProvider()

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        synonyms = self._generate_synonyms(term, slot)
        candidates: list[ConceptMapping] = []

        for synonym in synonyms:
            if _normalize_text(synonym) == _normalize_text(term):
                continue

            for provider in (self._ols, self._bioportal):
                for match in provider.lookup(slot, synonym):
                    candidates.append(
                        match.model_copy(
                            update={
                                "query_term": term,
                                "match_type": "ai_expanded_synonym",
                                "source": self.name,
                                "confidence": CONFIDENCE_BY_MATCH["ai_expanded_synonym"],
                                "explanation": (
                                    f"LLM suggested alias {synonym!r}; resolved via {provider.name}"
                                ),
                            }
                        )
                    )
        return candidates

    def _generate_synonyms(self, term: str, slot: str) -> list[str]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return []

        prompt = (
            "Generate up to {max_synonyms} alternative biomedical ontology search terms "
            "for normalizing the following text to a formal ontology term. "
            "Return ONLY a JSON array of strings.\n\n"
            "Facet type: {slot}\n"
            "Original text: {text}\n"
        ).format(max_synonyms=MAX_AI_SYNONYMS, slot=slot, text=term)

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
            logger.warning("LLM disambiguation failed for %r (%s): %s", term, slot, exc)
        return []
