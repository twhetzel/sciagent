"""Tests for OmicsDI structured facet evidence in dataset annotation."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import (
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_tissue_evidence_details,
)


def _breast_cancer_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="breast cancer",
            curie="MONDO:0007254",
            label="breast cancer",
            ontology="MONDO",
            synonyms=["breast cancer"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="breast",
            curie="UBERON:0000310",
            label="breast",
            ontology="UBERON",
            synonyms=["breast"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="Proteomics",
            curie="OBI:0000615",
            label="Proteomics",
            ontology="OBI",
            synonyms=["Proteomics"],
            source="curated",
        ),
    ]


def _omicsdi_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "OmicsDI",
        "accession": "PXD016061",
        "title": "Quantitative proteomic analysis for breast cancer",
        "description": "Proteome data of distant metastatic breast cancer FFPE tissue.",
        "metadata_fields": {
            "title": "Quantitative proteomic analysis for breast cancer",
            "summary": "Proteome data of distant metastatic breast cancer FFPE tissue.",
            "condition_or_disease": "Breast Cancer",
            "biosample_type": "Breast Cancer Cell Line, Breast Cancer Cell",
            "assay_method": "Mass Spectrometry, Shotgun proteomics, Proteomics",
            "taxon": "Homo sapiens (Human)",
        },
        "retrieval_strategy": "strict",
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_omicsdi_structured_fields_support_disease_tissue_and_assay_evidence():
    mappings = _breast_cancer_mappings()
    fields = _omicsdi_candidate().metadata_fields

    disease_present, disease_fields, _ = extract_disease_evidence_details(mappings[0], fields)
    tissue_present, tissue_fields, _, _ = extract_tissue_evidence_details(mappings[1], fields)
    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(mappings[2], fields)

    assert disease_present is True
    assert "condition_or_disease" in disease_fields
    assert tissue_present is True
    assert "biosample_type" in tissue_fields
    assert assay_present is True
    assert assay_fields == ["assay_method"]
    assert "Proteomics" in assay_terms


def test_omicsdi_annotation_marks_requested_facets_supported():
    mappings = _breast_cancer_mappings()
    annotated = annotate_dataset_candidates([_omicsdi_candidate()], mappings)
    candidate = annotated[0]

    assert len(candidate.matched_concepts) == 3
    assert candidate.observed_disease == "Breast Cancer"
    assert "Breast Cancer Cell" in (candidate.observed_tissue or "")
    assert not any("not supported by returned metadata" in msg for msg in candidate.why_partial)


def test_omicsdi_disease_evidence_without_title_keyword():
    mappings = _breast_cancer_mappings()
    candidate = _omicsdi_candidate(
        title="PXD016061",
        description="Quantitative mass spectrometry dataset.",
        metadata_fields={
            "title": "PXD016061",
            "summary": "Quantitative mass spectrometry dataset.",
            "condition_or_disease": "Breast Cancer",
            "biosample_type": "Breast Cancer Cell Line",
            "assay_method": "Mass Spectrometry, Proteomics",
            "omicsdi_omics_type": "Proteomics",
            "omicsdi_observed_assay": "proteomics",
        },
    )

    annotated = annotate_dataset_candidates([candidate], mappings)
    assert any(mapping.slot == "disease" for mapping in annotated[0].matched_concepts)


def _rna_seq_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0002117",
            label="RNA-seq",
            ontology="OBI",
            synonyms=["RNA-seq"],
            source="curated",
        ),
    ]


def test_omicsdi_transcriptomics_supports_rna_seq_evidence():
    mappings = _rna_seq_mappings()
    candidate = _omicsdi_candidate(
        accession="E-MTAB-123",
        title="UC colon study",
        description="Colon biopsy RNA profiling",
        metadata_fields={
            "title": "UC colon study",
            "summary": "Colon biopsy RNA profiling",
            "condition_or_disease": "ulcerative colitis",
            "biosample_type": "Colon",
            "assay_method": "Transcriptomics",
            "omicsdi_omics_type": "Transcriptomics",
            "omicsdi_observed_assay": "RNA-seq",
        },
    )

    annotated = annotate_dataset_candidates([candidate], mappings)
    assert any(mapping.slot == "assay" for mapping in annotated[0].matched_concepts)
    assert annotated[0].observed_assay == "RNA-seq"
    assert not any("requested RNA-seq, not supported" in msg for msg in annotated[0].why_partial)


def _ibd_metabolomics_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="inflammatory bowel disease",
            curie="MONDO:0005265",
            label="inflammatory bowel disease",
            ontology="MONDO",
            synonyms=["inflammatory bowel disease", "IBD"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="serum",
            curie="UBERON:0001977",
            label="serum",
            ontology="UBERON",
            synonyms=["serum", "blood serum"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="metabolomics",
            curie="OBI:0003782",
            label="metabolomics",
            ontology="OBI",
            synonyms=["metabolomics"],
            source="curated",
        ),
    ]


def test_omicsdi_metabolomics_supports_assay_when_technology_is_mass_spectrometry():
    mappings = _ibd_metabolomics_mappings()
    candidate = _omicsdi_candidate(
        accession="ST000899",
        title="Alterations in Lipid, Amino Acid, and Energy Metabolism in Serum",
        description="Metabolomics profiling of serum from IBD patients.",
        metadata_fields={
            "title": "Alterations in Lipid, Amino Acid, and Energy Metabolism in Serum",
            "summary": "Metabolomics profiling of serum from IBD patients.",
            "condition_or_disease": "inflammatory bowel disease",
            "biosample_type": "Blood",
            "assay_method": "Mass Spectrometry, ESI Mass Spectrometry",
            "omicsdi_omics_type": "Metabolomics",
            "omicsdi_observed_assay": "metabolomics",
        },
    )

    annotated = annotate_dataset_candidates([candidate], mappings)
    matched_slots = {mapping.slot for mapping in annotated[0].matched_concepts}

    assert "assay" in matched_slots
    assert "tissue" in matched_slots
    assert annotated[0].observed_assay == "metabolomics"
