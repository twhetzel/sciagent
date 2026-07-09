"""Tests for ProteomeXchange repository vocabulary mapping."""

from domain.repository_vocab import (
    map_term_to_proteomexchange_facet,
    resolve_proteomexchange_facet_value,
)
from domain.repository_vocab.proteomexchange_vocab import proteomexchange_assay_filter_clauses


def test_resolve_proteomexchange_disease_aliases():
    assert resolve_proteomexchange_facet_value("disease", "Alzheimer's disease") == "Alzheimer's disease"
    assert resolve_proteomexchange_facet_value("disease", "breast cancer") == "Breast cancer"
    assert resolve_proteomexchange_facet_value("disease", "asthma") == "asthma"


def test_resolve_proteomexchange_tissue_aliases():
    assert resolve_proteomexchange_facet_value("tissue", "brain") == "Brain"
    assert resolve_proteomexchange_facet_value("tissue", "lung") == "Lung"


def test_proteomexchange_assay_filter_clauses_default_to_proteomics():
    assert proteomexchange_assay_filter_clauses(None) == ['omics_type:"Proteomics"']
    assert proteomexchange_assay_filter_clauses("proteomics") == ['omics_type:"Proteomics"']


def test_map_term_to_proteomexchange_facet_returns_none_for_empty():
    assert map_term_to_proteomexchange_facet("disease", "") is None
    assert map_term_to_proteomexchange_facet("disease", None) is None
