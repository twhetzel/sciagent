"""Tests for ImmPort structured facet evidence in dataset annotation."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.evidence_extraction import (
    IMMPORT_ASSAY_FIELD,
    extract_assay_evidence_details,
    extract_disease_evidence_details,
    extract_tissue_evidence_details,
)
from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from domain.ranking import rank_annotated_candidates

ASTHMA_QUERY = "Find public immunology datasets for asthma PBMC flow cytometry."


def _asthma_pbmc_flow_mappings() -> list[ConceptMapping]:
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
            slot="tissue",
            query_term="PBMC",
            curie="CL:0000094",
            label="PBMC",
            ontology="CL",
            synonyms=["PBMC", "peripheral blood mononuclear cell"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="Flow Cytometry",
            curie="OBI:0000040",
            label="Flow Cytometry",
            ontology="OBI",
            synonyms=["Flow Cytometry", "flow cytometry", "flow-cytometry"],
            source="curated",
        ),
    ]


def _immport_candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "ImmPort",
        "accession": "SDY123",
        "title": "Asthma immunology study",
        "description": "Peripheral blood samples collected for immunophenotyping.",
        "metadata_fields": {
            "title": "Asthma immunology study",
            "summary": "Peripheral blood samples collected for immunophenotyping.",
            "condition_or_disease": "asthma",
            "biosample_type": "PBMC",
            "assay_method": "Flow Cytometry",
            "gdstype": "Flow Cytometry",
            "taxon": "Homo sapiens",
        },
        "retrieval_strategy": "strict",
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_immport_structured_fields_support_disease_tissue_assay_evidence():
    mappings = _asthma_pbmc_flow_mappings()
    fields = _immport_candidate().metadata_fields

    disease_present, disease_fields, _ = extract_disease_evidence_details(
        mappings[0],
        fields,
    )
    tissue_present, tissue_fields, _, tissue_type = extract_tissue_evidence_details(
        mappings[1],
        fields,
    )
    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(
        mappings[2],
        fields,
    )

    assert disease_present is True
    assert "condition_or_disease" in disease_fields
    assert tissue_present is True
    assert "biosample_type" in tissue_fields
    assert tissue_type == "direct"
    assert assay_present is True
    assert assay_fields == ["assay_method"]
    assert "Flow Cytometry" in assay_terms


def test_immport_annotation_marks_all_requested_facets_supported():
    mappings = _asthma_pbmc_flow_mappings()
    annotated = annotate_dataset_candidates([_immport_candidate()], mappings)
    candidate = annotated[0]

    assert len(candidate.matched_concepts) == 3
    assert candidate.observed_assay == "Flow Cytometry"
    assert candidate.observed_disease == "asthma"
    assert candidate.observed_tissue == "PBMC"
    assert not any("not supported by returned metadata" in msg for msg in candidate.why_partial)


def test_immport_assay_evidence_without_narrative_flow_cytometry_mention():
    mappings = _asthma_pbmc_flow_mappings()
    candidate = _immport_candidate(
        title="Immunology cohort SDY123",
        description="Longitudinal peripheral blood collection.",
        metadata_fields={
            "title": "Immunology cohort SDY123",
            "summary": "Longitudinal peripheral blood collection.",
            "condition_or_disease": "asthma",
            "biosample_type": "PBMC",
            "assay_method": "Flow Cytometry",
            "gdstype": "Flow Cytometry",
        },
    )

    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert breakdown is not None
    assert breakdown.assay.present is True
    assert IMMPORT_ASSAY_FIELD in breakdown.assay.fields


def test_grounded_pbmc_label_matches_immport_biosample_type_pbmc():
    interpreted = interpret_dataset_query(ASTHMA_QUERY)
    tissue_mapping = next(
        mapping
        for mapping in enrich_concept_mappings(ground_interpreted_query(interpreted))
        if mapping.slot == "tissue"
    )

    present, fields, terms, tissue_type = extract_tissue_evidence_details(
        tissue_mapping,
        {"biosample_type": "PBMC"},
    )

    assert tissue_mapping.label == "peripheral blood mononuclear cell"
    assert present is True
    assert fields == ["biosample_type"]
    assert terms == ["PBMC"]
    assert tissue_type == "direct"


def test_immport_comma_separated_facet_values_match():
    mappings = _asthma_pbmc_flow_mappings()
    fields = {
        "condition_or_disease": "asthma, allergic rhinitis",
        "biosample_type": "PBMC, Whole Blood",
        "assay_method": "Flow Cytometry, ELISA",
    }

    assay_present, assay_fields, assay_terms = extract_assay_evidence_details(
        mappings[2],
        fields,
    )

    assert assay_present is True
    assert assay_fields == ["assay_method"]
    assert "Flow Cytometry" in assay_terms
