"""
Facet-to-ontology policy aligned with OBO Foundry registry domains.

SciAgent dataset-discovery facets map to OBO Foundry `domain` tags (see
https://obofoundry.org/registry/ontologies.yml). Each binding records which
ontology prefixes are searched, accepted, and preferred for a facet slot.

Non-Foundry ontologies (e.g. EFO) may appear as extensions when widely used
for repository metadata; set `obo_foundry_domain=None` for those.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OntologyTier = Literal["primary", "fallback"]

# OBO Foundry registry domain labels → SciAgent facet slots that accept them.
# Disease also accepts phenotype-domain ontologies (HP) as a controlled fallback.
FACET_OBO_FOUNDRY_DOMAINS: dict[str, tuple[str, ...]] = {
    "disease": ("health", "phenotype"),
    "phenotype": ("phenotype",),
    "tissue": ("anatomy and development",),
    "assay": ("investigations", "biological systems"),
    "organism": ("organisms",),
}


@dataclass(frozen=True)
class OntologyBinding:
    """One ontology prefix authorized for a dataset-discovery facet slot."""

    slot: str
    ols_id: str
    curie_prefix: str
    obo_foundry_domain: str | None
    tier: OntologyTier
    rank: int


# Ordered bindings per slot (rank = preference within tier).
SLOT_ONTOLOGY_BINDINGS: tuple[OntologyBinding, ...] = (
    OntologyBinding("disease", "mondo", "MONDO", "health", "primary", 0),
    OntologyBinding("disease", "doid", "DOID", "health", "primary", 1),
    # EFO: EBI experimental-factor ontology; widely used though not OBO Foundry.
    OntologyBinding("disease", "efo", "EFO", None, "primary", 2),
    OntologyBinding("disease", "hp", "HP", "phenotype", "fallback", 3),
    OntologyBinding("phenotype", "hp", "HP", "phenotype", "primary", 0),
    OntologyBinding("tissue", "uberon", "UBERON", "anatomy and development", "primary", 0),
    OntologyBinding("tissue", "cl", "CL", "anatomy and development", "primary", 1),
    OntologyBinding("assay", "obi", "OBI", "investigations", "primary", 0),
    OntologyBinding("assay", "go", "GO", "biological systems", "primary", 1),
    OntologyBinding("organism", "ncbitaxon", "NCBITAXON", "organisms", "primary", 0),
)


def _bindings_for_slot(slot: str) -> list[OntologyBinding]:
    return [binding for binding in SLOT_ONTOLOGY_BINDINGS if binding.slot == slot]


def build_facet_ontologies() -> dict[str, list[str]]:
    """OLS/BioPortal ontology ids to query per facet slot."""
    result: dict[str, list[str]] = {}
    for binding in sorted(SLOT_ONTOLOGY_BINDINGS, key=lambda item: (item.slot, item.rank)):
        result.setdefault(binding.slot, []).append(binding.ols_id)
    return result


def build_slot_curie_prefixes() -> dict[str, tuple[str, ...]]:
    """Accepted CURIE namespace prefixes per facet slot."""
    result: dict[str, tuple[str, ...]] = {}
    for slot in FACET_OBO_FOUNDRY_DOMAINS:
        prefixes = tuple(
            f"{binding.curie_prefix}:"
            for binding in sorted(_bindings_for_slot(slot), key=lambda item: item.rank)
        )
        result[slot] = prefixes
    return result


def build_slot_ontology_preference() -> dict[str, list[str]]:
    """Ontology prefix preference order per facet slot."""
    result: dict[str, list[str]] = {}
    for slot in FACET_OBO_FOUNDRY_DOMAINS:
        result[slot] = [
            binding.curie_prefix
            for binding in sorted(_bindings_for_slot(slot), key=lambda item: item.rank)
        ]
    return result


def build_slot_primary_ontologies() -> dict[str, list[str]]:
    """Primary-tier ontology prefixes per facet slot."""
    result: dict[str, list[str]] = {}
    for slot in FACET_OBO_FOUNDRY_DOMAINS:
        result[slot] = [
            binding.curie_prefix
            for binding in sorted(_bindings_for_slot(slot), key=lambda item: item.rank)
            if binding.tier == "primary"
        ]
    return result


def build_slot_fallback_ontologies() -> dict[str, list[str]]:
    """Fallback-tier ontology prefixes per facet slot."""
    result: dict[str, list[str]] = {}
    for slot in FACET_OBO_FOUNDRY_DOMAINS:
        fallbacks = [
            binding.curie_prefix
            for binding in sorted(_bindings_for_slot(slot), key=lambda item: item.rank)
            if binding.tier == "fallback"
        ]
        if fallbacks:
            result[slot] = fallbacks
    return result


FACET_ONTOLOGIES = build_facet_ontologies()
SLOT_CURIE_PREFIXES = build_slot_curie_prefixes()
SLOT_ONTOLOGY_PREFERENCE = build_slot_ontology_preference()
SLOT_PRIMARY_ONTOLOGIES = build_slot_primary_ontologies()
SLOT_FALLBACK_ONTOLOGIES = build_slot_fallback_ontologies()
