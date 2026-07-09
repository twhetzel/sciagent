"""Tests for VDJServer repository vocabulary mapping."""

from domain.repository_vocab import map_term_to_vdjserver_facet, resolve_vdjserver_facet_value
from domain.repository_vocab.vdjserver_vocab import vdjserver_assay_filter


def test_resolve_vdjserver_organism_aliases():
    assert resolve_vdjserver_facet_value("organism", "human") == "NCBITAXON:9606"
    assert resolve_vdjserver_facet_value("organism", "mouse") == "NCBITAXON:10090"


def test_resolve_vdjserver_tissue_aliases():
    assert resolve_vdjserver_facet_value("tissue", "PBMC") == "blood"
    assert resolve_vdjserver_facet_value("tissue", "lung") == "lung"


def test_vdjserver_assay_filter_maps_bcr_to_locus():
    clause = vdjserver_assay_filter("BCR")
    assert clause == {
        "op": "=",
        "content": {
            "field": "sample.pcr_target.pcr_target_locus",
            "value": "IGH",
        },
    }


def test_vdjserver_assay_filter_maps_bcr_repertoire_to_locus():
    clause = vdjserver_assay_filter("BCR repertoire")
    assert clause == {
        "op": "=",
        "content": {
            "field": "sample.pcr_target.pcr_target_locus",
            "value": "IGH",
        },
    }


def test_map_term_to_vdjserver_facet_returns_none_for_empty():
    assert map_term_to_vdjserver_facet("disease", "") is None
    assert map_term_to_vdjserver_facet("disease", None) is None
