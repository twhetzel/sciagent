"""Tests for dataset-discovery score breakdown audit data."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate
from domain.ranking import rank_annotated_candidates


def _uc_colon_rna_human_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="ulcerative colitis",
            curie="MONDO:0005101",
            label="ulcerative colitis",
            ontology="MONDO",
            synonyms=["ulcerative colitis", "UC"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="colon",
            curie="UBERON:0001155",
            label="colon",
            ontology="UBERON",
            synonyms=["colon", "colonic"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0002117",
            label="RNA-seq",
            ontology="OBI",
            synonyms=["RNA-seq", "RNA sequencing"],
            source="curated",
        ),
        ConceptMapping(
            slot="organism",
            query_term="human",
            curie="NCBITaxon:9606",
            label="Homo sapiens",
            ontology="NCBITaxon",
            synonyms=["human", "Homo sapiens"],
            source="curated",
        ),
    ]


def _candidate(**overrides) -> DatasetCandidate:
    base = {
        "repository": "GEO",
        "accession": "GSE12345",
        "title": "RNA-seq of ulcerative colitis colon biopsies",
        "description": "Homo sapiens transcriptome profiling by high throughput sequencing",
        "metadata_fields": {
            "title": "RNA-seq of ulcerative colitis colon biopsies",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
        "retrieval_strategy": "strict",
    }
    base.update(overrides)
    return DatasetCandidate(**base)


def test_score_breakdown_populated_for_full_match():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate()
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert breakdown is not None
    assert breakdown.match_status == "full"
    assert breakdown.final_score == ranked[0].score
    assert breakdown.retrieval_strategy == "strict"
    assert breakdown.disease.present is True
    assert "title" in breakdown.disease.fields
    assert "ulcerative colitis" in breakdown.disease.matched_terms
    assert breakdown.tissue.present is True
    assert breakdown.tissue.evidence_type == "direct"
    assert breakdown.assay.present is True
    assert breakdown.organism.present is True
    assert breakdown.evidence_coverage == 1.0


def test_tissue_derived_model_evidence_type():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="Patient-derived colon organoids in ulcerative colitis",
        description="RNA-seq of colonoids from UC patients",
        metadata_fields={
            "title": "Patient-derived colon organoids in ulcerative colitis",
            "summary": "RNA-seq of colonoids from UC patients",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    assert ranked[0].score_breakdown.tissue.evidence_type == "derived_model"


def test_partial_match_breakdown_marks_missing_slots_absent():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="RNA-seq study at UC Berkeley",
        description="Expression profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq study at UC Berkeley",
            "summary": "Expression profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert breakdown.match_status == "partial"
    assert breakdown.disease.present is False
    assert breakdown.tissue.present is False
    assert breakdown.assay.present is True
    assert breakdown.organism.present is True
    assert breakdown.evidence_coverage < 1.0
