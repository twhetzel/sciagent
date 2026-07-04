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
    assert ranked[0].match_status == "full"
    assert breakdown.match_status == "full"
    assert breakdown.display_rank_score == ranked[0].score
    assert breakdown.evidence_score <= ranked[0].score
    assert breakdown.base_score > 0
    assert breakdown.rank_tier == 4.0
    assert breakdown.retrieval_strategy == "strict"
    assert breakdown.disease.present is True
    assert "title" in breakdown.disease.fields
    assert "ulcerative colitis" in breakdown.disease.matched_terms
    assert breakdown.tissue.present is True
    assert breakdown.tissue.evidence_type == "direct"
    assert breakdown.assay.present is True
    assert breakdown.organism.present is True
    assert breakdown.organism.evidence_source == "structured"
    assert breakdown.evidence_coverage == 1.0
    assert breakdown.warnings == ranked[0].metadata_warnings
    assert breakdown.evidence_conflicts == ranked[0].evidence_conflicts


def test_tissue_derived_model_evidence_type_and_status():
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

    breakdown = ranked[0].score_breakdown
    assert breakdown.tissue.evidence_type == "derived_model"
    assert ranked[0].match_status == "ambiguous_or_mixed"
    assert breakdown.match_status == "ambiguous_or_mixed"


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
    assert ranked[0].match_status == "partial"
    assert breakdown.match_status == "partial"
    assert breakdown.disease.present is False
    assert breakdown.tissue.present is False
    assert breakdown.assay.present is True
    assert breakdown.organism.present is True
    assert breakdown.evidence_coverage < 1.0


def test_mixed_assay_conflict_is_ambiguous_or_mixed():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="ChIP-seq of ulcerative colitis colon biopsies",
        description="Homo sapiens transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "ChIP-seq of ulcerative colitis colon biopsies",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert breakdown.evidence_conflicts
    assert any("conflict" in conflict.lower() for conflict in breakdown.evidence_conflicts)
    assert ranked[0].match_status == "ambiguous_or_mixed"
    assert breakdown.match_status == "ambiguous_or_mixed"


def test_multi_assay_including_requested_is_not_evidence_conflict():
    """ATAC-seq + RNA-seq studies should not conflict when RNA-seq was requested."""
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="Epigenetic Memory of IBD [RNA-seq]",
        description=(
            "We performed Assay for Transposase-Accessible Chromatin using sequencing "
            "(ATAC-seq) and bulk RNA-seq on organoids."
        ),
        metadata_fields={
            "title": "Epigenetic Memory of IBD [RNA-seq]",
            "summary": (
                "We performed Assay for Transposase-Accessible Chromatin using sequencing "
                "(ATAC-seq) and bulk RNA-seq on organoids."
            ),
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert breakdown.assay.present is True
    assert ranked[0].evidence_conflicts == []
    assert any("Multiple assay types" in warning for warning in ranked[0].metadata_warnings)
    assert ranked[0].match_status == "ambiguous_or_mixed"
    assert breakdown.match_status == "ambiguous_or_mixed"


def test_full_with_warnings_when_metadata_has_non_mixed_conflicts():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="RNA-seq of ulcerative colitis colon biopsies",
        description="Homo sapiens transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq of ulcerative colitis colon biopsies",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    annotated = [
        annotated[0].model_copy(
            update={
                "metadata_warnings": annotated[0].metadata_warnings
                + ["Sample metadata incomplete for disease stage."],
                "evidence_conflicts": annotated[0].evidence_conflicts
                + ["Manual review flagged inconsistent sample labels."],
            }
        )
    ]
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert ranked[0].match_status == "full_with_warnings"
    assert breakdown.match_status == "full_with_warnings"
    assert breakdown.warnings


def test_organism_narrative_source_marks_full_with_warnings():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="RNA-seq of ulcerative colitis colon biopsies in human patients",
        description="Transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq of ulcerative colitis colon biopsies in human patients",
            "summary": "Transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert breakdown.organism.present is True
    assert breakdown.organism.evidence_source == "narrative"
    assert ranked[0].match_status == "full_with_warnings"


def test_mouse_model_study_is_ambiguous_or_mixed():
    mappings = _uc_colon_rna_human_mappings()
    candidate = _candidate(
        title="Mouse model of ulcerative colitis in colon",
        description="RNA-seq of DSS-treated mouse colon",
        metadata_fields={
            "title": "Mouse model of ulcerative colitis in colon",
            "summary": "RNA-seq of DSS-treated mouse colon",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Mus musculus",
        },
    )
    annotated = annotate_dataset_candidates([candidate], mappings)
    ranked = rank_annotated_candidates(annotated, mappings)

    breakdown = ranked[0].score_breakdown
    assert ranked[0].match_status == "ambiguous_or_mixed"
    assert breakdown.match_status == "ambiguous_or_mixed"
    assert breakdown.warnings
