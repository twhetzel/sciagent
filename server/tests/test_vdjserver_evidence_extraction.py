"""Tests for VDJServer structured facet evidence in dataset annotation."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import (
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_tissue_evidence_details,
)


def _covid_blood_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="COVID-19",
            curie="MONDO:0100096",
            label="COVID-19",
            ontology="MONDO",
            synonyms=["COVID-19"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="blood",
            curie="UBERON:0000178",
            label="blood",
            ontology="UBERON",
            synonyms=["blood"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="BCR repertoire",
            curie="NCIT:C189103",
            label="B cell receptor repertoire sequencing",
            ontology="NCIT",
            synonyms=["BCR repertoire", "BCR", "IGH", "contains_ig"],
            source="curated",
        ),
    ]


def _vdjserver_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "VDJServer",
        "accession": "PRJNA123456",
        "title": "COVID-19 BCR repertoire study",
        "description": "Peripheral blood BCR repertoire in COVID-19.",
        "metadata_fields": {
            "title": "COVID-19 BCR repertoire study",
            "summary": "Peripheral blood BCR repertoire in COVID-19.",
            "condition_or_disease": "COVID-19",
            "biosample_type": "blood",
            "assay_method": "IGH, Illumina HiSeq, contains_ig",
            "taxon": "Homo sapiens",
        },
        "retrieval_strategy": "strict",
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_vdjserver_structured_fields_support_disease_tissue_and_assay_evidence():
    mappings = _covid_blood_mappings()
    fields = _vdjserver_candidate().metadata_fields

    disease_present, disease_fields, _ = extract_disease_evidence_details(mappings[0], fields)
    tissue_present, tissue_fields, _, _ = extract_tissue_evidence_details(mappings[1], fields)
    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(mappings[2], fields)

    assert disease_present is True
    assert "condition_or_disease" in disease_fields
    assert tissue_present is True
    assert "biosample_type" in tissue_fields
    assert assay_present is True
    assert "assay_method" in assay_fields
    assert "IGH" in assay_terms or "b cell receptor repertoire sequencing" in {
        term.lower() for term in assay_terms
    }


def test_vdjserver_annotation_marks_requested_facets_supported():
    mappings = _covid_blood_mappings()
    annotated = annotate_dataset_candidates([_vdjserver_candidate()], mappings)
    candidate = annotated[0]

    assert len(candidate.matched_concepts) == 3
    assert candidate.observed_disease == "COVID-19"
    assert candidate.observed_tissue == "blood"
    assert not any("not supported by returned metadata" in msg for msg in candidate.why_partial)
