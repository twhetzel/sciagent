"""ImmPort Shared Data lookup-table vocabulary loader and facet resolver."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

import requests

logger = logging.getLogger(__name__)

IMMPORT_LOOKUP_BASE = "https://www.immport.org/data/query/api/lookup"
REQUEST_TIMEOUT = 20

SLOT_LOOKUP_TABLES: dict[str, str] = {
    "disease": "lkDisease",
    "tissue": "lkSampleType",
    "assay": "lkExpMeasurementTech",
    "organism": "lkSpecies",
}

# Static overrides kept as safety net when lookup tables lag or offline.
STATIC_FACET_OVERRIDES: dict[tuple[str, str], str] = {
    ("assay", "flow cytometry"): "Flow Cytometry",
    ("tissue", "pbmc"): "PBMC",
    ("tissue", "pbmcs"): "PBMC",
    ("tissue", "t cell"): "T cell",
    ("tissue", "t cells"): "T cell",
    ("tissue", "b cell"): "B cell",
    ("tissue", "b cells"): "B cell",
    ("tissue", "nk cell"): "NK cell",
    ("tissue", "nk cells"): "NK cell",
    ("organism", "human"): "Homo sapiens",
    ("organism", "homo sapiens"): "Homo sapiens",
}


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class ImmPortVocabulary:
    """Lazy loader for ImmPort lookup tables used in facet search."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def load_table(self, table_name: str) -> list[dict[str, Any]]:
        if table_name in self._tables:
            return self._tables[table_name]

        url = f"{IMMPORT_LOOKUP_BASE}/{table_name}"
        try:
            response = requests.get(url, params={"format": "json"}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("ImmPort lookup fetch failed for %s: %s", table_name, exc)
            self._tables[table_name] = []
            return []

        if not isinstance(payload, list):
            logger.warning("Unexpected ImmPort lookup payload for %s", table_name)
            self._tables[table_name] = []
            return []

        self._tables[table_name] = payload
        return payload

    def entries_for_slot(self, slot: str) -> list[dict[str, Any]]:
        table_name = SLOT_LOOKUP_TABLES.get(slot)
        if not table_name:
            return []
        return self.load_table(table_name)

    def resolve(self, slot: str, term: str | None) -> str | None:
        """Map a user or ontology label to an ImmPort controlled vocabulary name."""
        if not term or not str(term).strip():
            return None

        normalized = _normalize_key(term)
        override = STATIC_FACET_OVERRIDES.get((slot, normalized))
        if override:
            return override

        entries = self.entries_for_slot(slot)
        if not entries:
            return term.strip()

        prefix_matches: list[tuple[int, str]] = []

        for entry in entries:
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            name_key = _normalize_key(name)
            if name_key == normalized:
                return name
            if normalized in name_key or name_key in normalized:
                prefix_matches.append((abs(len(name_key) - len(normalized)), name))

        if prefix_matches:
            prefix_matches.sort(key=lambda item: item[0])
            return prefix_matches[0][1]

        description_matches: list[tuple[int, str]] = []
        for entry in entries:
            name = str(entry.get("name") or "").strip()
            description = _normalize_key(str(entry.get("description") or ""))
            if not name:
                continue
            if normalized in description:
                description_matches.append((len(name), name))

        if description_matches:
            description_matches.sort(key=lambda item: item[0])
            return description_matches[0][1]

        return term.strip()


@lru_cache(maxsize=1)
def _default_vocabulary() -> ImmPortVocabulary:
    return ImmPortVocabulary()


def resolve_immport_facet_value(slot: str, term: str | None) -> str | None:
    """Resolve one facet term to an ImmPort lookup-table value."""
    return _default_vocabulary().resolve(slot, term)


def map_term_to_immport_facet(slot: str, term: str | None) -> dict[str, str | None]:
    """Return mapped ImmPort facet value plus resolution metadata for tracing."""
    resolved = resolve_immport_facet_value(slot, term)
    return {
        "slot": slot,
        "input": term or "",
        "immport_value": resolved,
        "mapped": resolved is not None and resolved != (term or "").strip(),
    }
