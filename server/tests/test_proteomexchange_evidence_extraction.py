"""Tests for ProteomeXchange structured facet evidence in dataset annotation."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import (
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_tissue_evidence_details,
)


def _alzheimer_brain_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="Alzheimer disease",
            curie="MONDO:0004975",
            label="Alzheimer disease",
            ontology="MONDO",
            synonyms=["Alzheimer disease"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="brain",
            curie="UBERON:0000955",
            label="brain",
            ontology="UBERON",
            synonyms=["brain"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="proteomics",
            curie="OBI:0000615",
            label="proteomics",
            ontology="OBI",
            synonyms=["proteomics"],
            source="curated",
        ),
    ]


def _proteomexchange_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "ProteomeXchange",
        "accession": "PXD012203",
        "title": "Proteomics of Brain Proteome in Alzheimer Disease",
        "description": "Brain tissue proteomics in Alzheimer disease.",
        "metadata_fields": {
            "title": "Proteomics of Brain Proteome in Alzheimer Disease",
            "summary": "Brain tissue proteomics in Alzheimer disease.",
            "condition_or_disease": "Alzheimer's disease",
            "biosample_type": "Brain",
            "assay_method": "Mass Spectrometry, Proteomics",
            "omicsdi_omics_type": "Proteomics",
            "omicsdi_observed_assay": "proteomics",
            "taxon": "Homo sapiens (Human)",
        },
        "retrieval_strategy": "strict",
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_proteomexchange_structured_fields_support_disease_tissue_and_assay_evidence():
    mappings = _alzheimer_brain_mappings()
    fields = _proteomexchange_candidate().metadata_fields

    disease_present, disease_fields, _ = extract_disease_evidence_details(mappings[0], fields)
    tissue_present, tissue_fields, _, _ = extract_tissue_evidence_details(mappings[1], fields)
    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(mappings[2], fields)

    assert disease_present is True
    assert "condition_or_disease" in disease_fields
    assert tissue_present is True
    assert "biosample_type" in tissue_fields
    assert assay_present is True
    assert any(term.lower() == "proteomics" for term in assay_terms)


def test_proteomexchange_annotation_marks_requested_facets_supported():
    mappings = _alzheimer_brain_mappings()
    annotated = annotate_dataset_candidates([_proteomexchange_candidate()], mappings)
    candidate = annotated[0]

    assert len(candidate.matched_concepts) == 3
    assert candidate.observed_disease == "Alzheimer's disease"
    assert candidate.observed_tissue == "Brain"
    assert not any("not supported by returned metadata" in msg for msg in candidate.why_partial)


def test_proteomexchange_disease_evidence_without_title_keyword():
    mappings = _alzheimer_brain_mappings()
    candidate = _proteomexchange_candidate(
        title="PXD012203",
        description="Quantitative mass spectrometry dataset.",
        metadata_fields={
            "title": "PXD012203",
            "summary": "Quantitative mass spectrometry dataset.",
            "condition_or_disease": "Alzheimer's disease",
            "biosample_type": "Brain",
            "assay_method": "Mass Spectrometry, Proteomics",
            "omicsdi_omics_type": "Proteomics",
            "omicsdi_observed_assay": "proteomics",
        },
    )

    annotated = annotate_dataset_candidates([candidate], mappings)
    assert any(mapping.slot == "disease" for mapping in annotated[0].matched_concepts)
