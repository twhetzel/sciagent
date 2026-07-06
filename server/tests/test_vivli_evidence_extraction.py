"""Tests for Vivli structured facet evidence in dataset annotation."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import (
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_tissue_evidence_details,
)


def _asthma_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="asthma",
            curie="MONDO:0004979",
            label="asthma",
            ontology="MONDO",
            synonyms=["asthma"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="Randomized Clinical Trial",
            curie="OBI:0000070",
            label="Randomized Clinical Trial",
            ontology="OBI",
            synonyms=["Randomized Clinical Trial"],
            source="curated",
        ),
    ]


def _vivli_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "Vivli",
        "accession": "NCT00939341",
        "title": "Asthma SMARTASIA trial",
        "description": "Symbicort maintenance and reliever therapy in asthma patients.",
        "metadata_fields": {
            "title": "Asthma SMARTASIA trial",
            "summary": "Symbicort maintenance and reliever therapy in asthma patients.",
            "condition_or_disease": "asthma",
            "assay_method": "Randomized Clinical Trial",
            "taxon": "Homo sapiens",
        },
        "retrieval_strategy": "strict",
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_vivli_structured_fields_support_disease_and_assay_evidence():
    mappings = _asthma_mappings()
    fields = _vivli_candidate().metadata_fields

    disease_present, disease_fields, _ = extract_disease_evidence_details(
        mappings[0],
        fields,
    )
    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(
        mappings[1],
        fields,
    )

    assert disease_present is True
    assert "condition_or_disease" in disease_fields
    assert assay_present is True
    assert assay_fields == ["assay_method"]
    assert "Randomized Clinical Trial" in assay_terms


def test_vivli_annotation_marks_requested_facets_supported():
    mappings = _asthma_mappings()
    annotated = annotate_dataset_candidates([_vivli_candidate()], mappings)
    candidate = annotated[0]

    assert len(candidate.matched_concepts) == 2
    assert candidate.observed_disease == "asthma"
    assert candidate.observed_assay == "Randomized Clinical Trial"
    assert not any("not supported by returned metadata" in msg for msg in candidate.why_partial)


def test_vivli_disease_evidence_without_title_keyword():
    mappings = _asthma_mappings()
    candidate = _vivli_candidate(
        title="Clinical trial NCT00939341",
        description="Phase III maintenance therapy study.",
        metadata_fields={
            "title": "Clinical trial NCT00939341",
            "summary": "Phase III maintenance therapy study.",
            "condition_or_disease": "asthma",
            "assay_method": "Randomized Clinical Trial",
        },
    )

    present, fields, terms, tissue_type = extract_tissue_evidence_details(
        ConceptMapping(
            slot="tissue",
            query_term="Study Subject",
            curie="NCIT:C41189",
            label="Study Subject",
            ontology="NCIT",
            synonyms=["Study Subject"],
            source="curated",
        ),
        candidate.metadata_fields,
    )

    assert present is False
    assert tissue_type == "absent"

    annotated = annotate_dataset_candidates([candidate], mappings)
    assert any(mapping.slot == "disease" for mapping in annotated[0].matched_concepts)
