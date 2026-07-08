"""Tests for AIRR repertoire assay evidence normalization."""

from domain.airr_assay import (
    airr_supports_requested_assay,
    annotate_airr_metadata_fields,
    infer_observed_assay_from_airr_metadata,
)
from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query


def test_infer_observed_assay_from_igh_locus():
    assert (
        infer_observed_assay_from_airr_metadata(assay_method="IGH, Illumina HiSeq, contains_ig")
        == "B cell receptor repertoire sequencing"
    )


def test_airr_supports_bcr_repertoire_from_igh_metadata():
    assert airr_supports_requested_assay(
        assay_method="IGH, Illumina HiSeq, contains_ig",
        requested_label="B cell receptor repertoire sequencing",
    )
    assert airr_supports_requested_assay(
        assay_method="IGH, Illumina HiSeq, contains_ig",
        requested_label="BCR repertoire",
    )


def test_annotate_airr_metadata_fields_adds_observed_assay():
    fields = annotate_airr_metadata_fields(
        {"assay_method": "TRB, Illumina MiSeq, contains_tr"},
        assay_method="TRB, Illumina MiSeq, contains_tr",
    )
    assert fields["airr_observed_assay"] == "T cell receptor repertoire sequencing"


def test_covid_bcr_query_grounds_assay_to_ncit_and_supports_evidence():
    interpreted = interpret_dataset_query("Find public BCR repertoire datasets for COVID-19 blood.")
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))
    assay = next(mapping for mapping in mappings if mapping.slot == "assay")

    assert assay.curie == "NCIT:C189103"
    assert assay.label == "B cell receptor repertoire sequencing"

    candidate = DatasetCandidate(
        repository="VDJServer",
        accession="PRJNA123",
        title="COVID study",
        description="",
        metadata_fields=annotate_airr_metadata_fields(
            {
                "condition_or_disease": "COVID-19",
                "biosample_type": "blood",
                "assay_method": "IGH, Illumina HiSeq, contains_ig",
                "title": "COVID study",
                "summary": "COVID study",
            },
            assay_method="IGH, Illumina HiSeq, contains_ig",
        ),
    )
    annotated = annotate_dataset_candidates([candidate], mappings)[0]
    assert any(mapping.slot == "assay" for mapping in annotated.matched_concepts)
    assert not any("assay evidence treated as missing" in msg for msg in annotated.why_partial)
