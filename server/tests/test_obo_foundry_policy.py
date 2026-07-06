"""Tests for OBO Foundry domain-aligned facet ontology policy."""

from __future__ import annotations

from domain.ontology_providers.obo_foundry_policy import (
    FACET_OBO_FOUNDRY_DOMAINS,
    FACET_ONTOLOGIES,
    SLOT_CURIE_PREFIXES,
    SLOT_ONTOLOGY_BINDINGS,
    SLOT_PRIMARY_ONTOLOGIES,
    build_slot_curie_prefixes,
    build_slot_ontology_preference,
)


def test_facet_domains_cover_key_ontologies():
    domains_by_prefix = {
        binding.curie_prefix: binding.obo_foundry_domain
        for binding in SLOT_ONTOLOGY_BINDINGS
        if binding.obo_foundry_domain
    }
    assert domains_by_prefix["MONDO"] == "health"
    assert domains_by_prefix["DOID"] == "health"
    assert domains_by_prefix["UBERON"] == "anatomy and development"
    assert domains_by_prefix["CL"] == "anatomy and development"
    assert domains_by_prefix["OBI"] == "investigations"
    assert domains_by_prefix["GO"] == "biological systems"
    assert domains_by_prefix["HP"] == "phenotype"
    assert domains_by_prefix["NCBITAXON"] == "organisms"


def test_bindings_domain_matches_facet_policy():
    for binding in SLOT_ONTOLOGY_BINDINGS:
        if binding.obo_foundry_domain is None:
            continue
        allowed = FACET_OBO_FOUNDRY_DOMAINS[binding.slot]
        assert binding.obo_foundry_domain in allowed


def test_derived_tables_are_consistent():
    assert FACET_ONTOLOGIES["disease"] == ["mondo", "doid", "efo", "hp"]
    assert FACET_ONTOLOGIES["tissue"] == ["uberon", "cl"]
    assert SLOT_CURIE_PREFIXES == build_slot_curie_prefixes()
    assert SLOT_PRIMARY_ONTOLOGIES["disease"] == ["MONDO", "DOID", "EFO"]
    assert SLOT_PRIMARY_ONTOLOGIES["tissue"] == ["UBERON", "CL"]
    assert "CL:" in SLOT_CURIE_PREFIXES["tissue"]
    assert build_slot_ontology_preference()["assay"] == ["OBI", "GO"]
