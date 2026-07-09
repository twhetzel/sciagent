"""Tests for OmicsDI repository vocabulary resolver."""

from domain.repository_vocab import map_term_to_omicsdi_facet, resolve_omicsdi_facet_value
from domain.repository_vocab.omicsdi_vocab import omicsdi_assay_filter_clauses


def test_resolve_omicsdi_disease_aliases():
    assert resolve_omicsdi_facet_value("disease", "UC") == "ulcerative colitis"
    assert resolve_omicsdi_facet_value("disease", "Alzheimer's disease") == "Alzheimer's disease"


def test_resolve_omicsdi_assay_aliases():
    assert resolve_omicsdi_facet_value("assay", "RNA-seq") == "Transcriptomics"
    assert resolve_omicsdi_facet_value("assay", "proteomics") == "Proteomics"
    assert resolve_omicsdi_facet_value("assay", "metabolomics") == "Metabolomics"


def test_resolve_omicsdi_tissue_serum():
    assert resolve_omicsdi_facet_value("tissue", "serum") == "Serum"
    assert resolve_omicsdi_facet_value("tissue", "blood serum") == "Serum"


def test_omicsdi_assay_filter_clauses():
    assert omicsdi_assay_filter_clauses("Transcriptomics") == ['omics_type:"Transcriptomics"']
    assert omicsdi_assay_filter_clauses("Mass Spectrometry") == [
        'technology_type:"Mass Spectrometry"'
    ]


def test_map_term_to_omicsdi_facet_returns_none_for_empty():
    assert map_term_to_omicsdi_facet("disease", "") is None
    assert map_term_to_omicsdi_facet("disease", None) is None
