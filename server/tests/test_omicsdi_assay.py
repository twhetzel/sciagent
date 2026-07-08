"""Tests for OmicsDI omics_type to assay normalization."""

from domain.omicsdi_assay import (
    annotate_omicsdi_metadata_fields,
    infer_observed_assay_from_omicsdi_metadata,
    omicsdi_supports_requested_assay,
)


def test_transcriptomics_maps_to_rna_seq():
    assert (
        infer_observed_assay_from_omicsdi_metadata(omics_type="Transcriptomics")
        == "RNA-seq"
    )


def test_proteomics_maps_to_proteomics():
    assert (
        infer_observed_assay_from_omicsdi_metadata(
            omics_type="Proteomics",
            assay_method="Mass Spectrometry, Shotgun proteomics",
        )
        == "proteomics"
    )


def test_metabolomics_omics_type_takes_priority_over_mass_spectrometry_technology():
    assert (
        infer_observed_assay_from_omicsdi_metadata(
            omics_type="Metabolomics",
            assay_method="Mass Spectrometry, ESI Mass Spectrometry",
        )
        == "metabolomics"
    )


def test_metabolomics_maps_to_metabolomics():
    assert (
        infer_observed_assay_from_omicsdi_metadata(omics_type="Metabolomics")
        == "metabolomics"
    )


def test_omicsdi_supports_metabolomics_from_omics_type():
    assert omicsdi_supports_requested_assay(
        omics_type="Metabolomics",
        assay_method="Mass Spectrometry, ESI",
        requested_label="metabolomics",
    )


def test_omicsdi_supports_rna_seq_from_transcriptomics():
    assert omicsdi_supports_requested_assay(
        omics_type="Transcriptomics",
        assay_method="",
        requested_label="RNA-seq",
    )


def test_annotate_omicsdi_metadata_fields_sets_observed_assay():
    fields = annotate_omicsdi_metadata_fields(
        {"title": "Study", "summary": "Colon RNA profiling"},
        omics_type="Transcriptomics",
        assay_method="Transcriptomics",
    )
    assert fields["omicsdi_omics_type"] == "Transcriptomics"
    assert fields["omicsdi_observed_assay"] == "RNA-seq"
