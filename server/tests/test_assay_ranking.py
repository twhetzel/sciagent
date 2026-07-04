"""Tests for assay-aware integrated dataset ranking."""

from __future__ import annotations

from domain.assay_ranking import (
    PARTIAL_ASSAY_MISMATCH,
    PARTIAL_ASSAY_SUPPORTED,
    compute_assay_rank_adjustment,
    compute_rank_tier,
    detect_assay_mismatch,
    validate_rna_seq_assay_ranking,
)
from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping, DatasetCandidate, ScoreBreakdown
from domain.ranking import rank_annotated_candidates
from tools.expression_atlas import normalize_gxa_record


def _uc_rnaseq_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="ulcerative colitis",
            curie="MONDO:0005101",
            label="ulcerative colitis",
            ontology="MONDO",
            synonyms=["ulcerative colitis"],
            source="curated",
        ),
        ConceptMapping(
            slot="tissue",
            query_term="colon",
            curie="UBERON:0001155",
            label="colon",
            ontology="UBERON",
            synonyms=["colon"],
            source="curated",
        ),
        ConceptMapping(
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0002117",
            label="RNA-seq",
            ontology="OBI",
            synonyms=["RNA-seq"],
            source="curated",
        ),
        ConceptMapping(
            slot="organism",
            query_term="human",
            curie="NCBITaxon:9606",
            label="Homo sapiens",
            ontology="NCBITaxon",
            synonyms=["human"],
            source="curated",
        ),
    ]


def test_detect_assay_mismatch_for_gxa_proteomics():
    mappings = _uc_rnaseq_mappings()
    mismatch, note = detect_assay_mismatch(
        mappings[2],
        "proteomics",
        accession="E-PROT-40",
    )
    assert mismatch is True
    assert "E-PROT" in note


def test_detect_assay_mismatch_false_for_rna_seq_observed():
    mappings = _uc_rnaseq_mappings()
    mismatch, note = detect_assay_mismatch(mappings[2], "RNA-seq")
    assert mismatch is False
    assert note == ""


def test_proteomics_partial_ranks_below_rna_seq_supported_partial():
    mappings = _uc_rnaseq_mappings()
    rnaseq_partial = DatasetCandidate(
        repository="GEO",
        accession="GSEPARTIAL",
        title="RNA-seq transcriptome profiling in human blood samples",
        description="Homo sapiens transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq transcriptome profiling in human blood samples",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    proteomics = normalize_gxa_record(
        {
            "accession": "E-PROT-40",
            "title": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "description": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "species": "Homo sapiens",
            "experiment_type": "proteomics_pr_matrix",
        }
    )
    assert proteomics is not None

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([proteomics, rnaseq_partial], mappings),
        mappings,
    )

    assert ranked[0].accession == "GSEPARTIAL"
    assert ranked[0].observed_assay == "RNA-seq"
    assert ranked[1].accession == "E-PROT-40"
    assert ranked[1].assay_mismatch is True
    assert ranked[1].match_status == "partial"
    assert ranked[1].score_breakdown.partial_assay_subtype == PARTIAL_ASSAY_MISMATCH
    assert ranked[1].score_breakdown.rank_tier == 2.2
    assert ranked[0].score_breakdown.partial_assay_subtype == PARTIAL_ASSAY_SUPPORTED
    assert ranked[0].score_breakdown.rank_tier == 2.8
    assert validate_rna_seq_assay_ranking(mappings, ranked, top_n=2) == []


def test_proteomics_partial_ranks_below_rna_seq_geo_partial():
    mappings = _uc_rnaseq_mappings()
    rnaseq_geo = DatasetCandidate(
        repository="GEO",
        accession="E-GEOD-83687",
        title="RNA-seq of inflammatory bowel disease patients",
        description="Homo sapiens transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq of inflammatory bowel disease patients",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    proteomics = normalize_gxa_record(
        {
            "accession": "E-PROT-40",
            "title": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "description": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "species": "Homo sapiens",
            "experiment_type": "proteomics_pr_matrix",
        }
    )
    assert proteomics is not None

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([proteomics, rnaseq_geo], mappings),
        mappings,
    )

    assert ranked[0].accession == "E-GEOD-83687"
    assert ranked[1].accession == "E-PROT-40"
    assert ranked[0].score > ranked[1].score


def test_microarray_partial_ranks_below_rna_seq_with_assay_evidence():
    mappings = _uc_rnaseq_mappings()
    rnaseq = normalize_gxa_record(
        {
            "accession": "E-MTAB-7860",
            "title": "RNA-seq of biopsies from ulcerative colitis patients",
            "description": "RNA-seq of biopsies from ulcerative colitis patients",
            "species": "Homo sapiens",
            "experiment_type": "rnaseq_mrna_differential",
        }
    )
    microarray = normalize_gxa_record(
        {
            "accession": "E-GEOD-65114",
            "title": "Microarray analysis of colonic mucosal biopsies from ulcerative colitis patients",
            "description": "Microarray analysis of colonic mucosal biopsies from ulcerative colitis patients",
            "species": "Homo sapiens",
            "experiment_type": "microarray_1colour_mrna_differential",
        }
    )
    assert rnaseq is not None and microarray is not None

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([microarray, rnaseq], mappings),
        mappings,
    )

    assert ranked[0].accession == "E-MTAB-7860"
    assert ranked[1].assay_mismatch is True
    assert ranked[1].observed_assay == "microarray"


def test_compute_assay_rank_adjustment_exposes_mismatch_note():
    mappings = _uc_rnaseq_mappings()
    candidate = DatasetCandidate(
        repository="Expression Atlas",
        accession="E-PROT-39",
        title="Proteomics of brain proteome in Alzheimer disease",
        description="Proteomics of brain proteome in Alzheimer disease",
        observed_assay="proteomics",
        metadata_fields={"title": "Proteomics of brain proteome in Alzheimer disease"},
    )
    breakdown = ScoreBreakdown()

    adjustment, mismatch, note = compute_assay_rank_adjustment(
        candidate,
        breakdown,
        mappings[2],
    )

    assert mismatch is True
    assert adjustment < 0
    assert "Requested RNA-seq" in note
