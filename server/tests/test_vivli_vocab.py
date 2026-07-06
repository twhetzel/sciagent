"""Tests for Vivli repository vocabulary resolver."""

from domain.repository_vocab import map_term_to_vivli_facet, resolve_vivli_facet_value


def test_resolve_vivli_disease_aliases():
    assert resolve_vivli_facet_value("disease", "covid-19") == "COVID-19"
    assert resolve_vivli_facet_value("disease", "UC") == "ulcerative colitis"


def test_map_term_to_vivli_facet_returns_none_for_empty():
    assert map_term_to_vivli_facet("disease", "") is None
    assert map_term_to_vivli_facet("disease", None) is None


def test_resolve_vivli_assay_aliases():
    assert resolve_vivli_facet_value("assay", "RNA-seq") == "RNA-seq"
    assert resolve_vivli_facet_value("assay", "flow cytometry") == "Flow Cytometry"
