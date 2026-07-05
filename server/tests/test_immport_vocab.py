"""Tests for ImmPort repository vocabulary mapping."""

from domain.repository_vocab.immport_vocab import ImmPortVocabulary


DISEASE_TABLE = [
    {"name": "asthma", "description": "A bronchial disease"},
    {"name": "ulcerative colitis", "description": "Inflammatory bowel disease"},
]

SAMPLE_TABLE = [
    {"name": "PBMC", "description": "Peripheral Blood Mononuclear Cell"},
    {"name": "Colon", "description": "Colon tissue"},
]

ASSAY_TABLE = [
    {"name": "Flow Cytometry", "description": "FACS"},
    {"name": "RNA-seq", "description": "RNA sequencing"},
]


def test_resolve_uses_exact_lookup_name():
    vocab = ImmPortVocabulary()
    vocab._tables["lkDisease"] = DISEASE_TABLE
    vocab._tables["lkSampleType"] = SAMPLE_TABLE
    vocab._tables["lkExpMeasurementTech"] = ASSAY_TABLE

    assert vocab.resolve("disease", "asthma") == "asthma"
    assert vocab.resolve("tissue", "PBMC") == "PBMC"
    assert vocab.resolve("assay", "flow cytometry") == "Flow Cytometry"


def test_resolve_falls_back_to_input_when_table_empty():
    vocab = ImmPortVocabulary()
    assert vocab.resolve("disease", "rare condition") == "rare condition"
