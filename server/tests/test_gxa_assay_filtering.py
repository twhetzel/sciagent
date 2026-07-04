"""Tests for Expression Atlas assay filtering in dataset discovery."""

from __future__ import annotations

from domain.dataset_annotation import annotate_dataset_candidates
from domain.dataset_search import ConceptMapping
from domain.gxa_assay import infer_observed_assay_from_gxa_experiment_type
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


def test_infer_observed_assay_from_gxa_experiment_type():
    assert infer_observed_assay_from_gxa_experiment_type("rnaseq_mrna_differential") == "RNA-seq"
    assert infer_observed_assay_from_gxa_experiment_type("microarray_1colour_mrna_differential") == "microarray"
    assert infer_observed_assay_from_gxa_experiment_type("proteomics_pr_matrix") == "proteomics"


def test_normalize_gxa_record_sets_structured_assay_metadata():
    candidate = normalize_gxa_record(
        {
            "accession": "E-PROT-40",
            "title": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "description": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "species": "Homo sapiens",
            "experiment_type": "proteomics_pr_matrix",
        }
    )

    assert candidate is not None
    assert candidate.metadata_fields["gxa_experiment_type"] == "proteomics_pr_matrix"
    assert candidate.metadata_fields["gxa_observed_assay"] == "proteomics"


def test_gxa_proteomics_does_not_receive_rna_seq_assay_credit():
    mappings = _uc_rnaseq_mappings()
    candidate = normalize_gxa_record(
        {
            "accession": "E-PROT-40",
            "title": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "description": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "species": "Homo sapiens",
            "experiment_type": "proteomics_pr_matrix",
        }
    )
    assert candidate is not None

    annotated = annotate_dataset_candidates([candidate], mappings)[0]

    assert annotated.observed_assay == "proteomics"
    assert annotated.assay_mismatch is True
    assert all(mapping.slot != "assay" for mapping in annotated.matched_concepts)
    assert any("Assay mismatch:" in warning for warning in annotated.metadata_warnings)
    assert any("Assay mismatch:" in reason for reason in annotated.why_partial)


def test_gxa_microarray_is_partial_without_rna_seq_assay_match():
    mappings = _uc_rnaseq_mappings()
    candidate = normalize_gxa_record(
        {
            "accession": "E-GEOD-65114",
            "title": "Microarray analysis of colonic mucosal biopsies from ulcerative colitis patients",
            "description": "Microarray analysis of colonic mucosal biopsies from ulcerative colitis patients",
            "species": "Homo sapiens",
            "experiment_type": "microarray_1colour_mrna_differential",
        }
    )
    assert candidate is not None

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([candidate], mappings),
        mappings,
    )

    assert ranked[0].observed_assay == "microarray"
    assert ranked[0].match_status == "partial"
    assert all(mapping.slot != "assay" for mapping in ranked[0].matched_concepts)


def test_gxa_rnaseq_receives_assay_credit_and_ranks_above_mismatch():
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
    proteomics = normalize_gxa_record(
        {
            "accession": "E-PROT-40",
            "title": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "description": "Human colon biopsies (healthy and Ulcerative Colitis) LC-MS/MS",
            "species": "Homo sapiens",
            "experiment_type": "proteomics_pr_matrix",
        }
    )
    assert rnaseq is not None and proteomics is not None

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([proteomics, rnaseq], mappings),
        mappings,
    )

    assert ranked[0].accession == "E-MTAB-7860"
    assert any(mapping.slot == "assay" for mapping in ranked[0].matched_concepts)
    assert ranked[1].accession == "E-PROT-40"
    assert ranked[1].match_status == "partial"
    assert ranked[1].assay_mismatch is True
