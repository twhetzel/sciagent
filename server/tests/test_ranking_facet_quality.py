"""Tests for facet-aware ranking adjustments."""

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


def _candidate(accession: str, **overrides) -> DatasetCandidate:
    base = {
        "repository": "GEO",
        "accession": accession,
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


def test_exact_uc_match_ranks_above_related_crohns_partial_match():
    mappings = _uc_colon_rna_human_mappings()
    exact = _candidate("GSE334803")
    crohns_partial = _candidate(
        "E-GEOD-57945",
        title="RNA-seq of pediatric patients with Crohn's disease and ulcerative colitis controls in colon",
        description="Homo sapiens transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq of pediatric patients with Crohn's disease in colon",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([crohns_partial, exact], mappings),
        mappings,
    )

    assert ranked[0].accession == "GSE334803"
    assert ranked[0].match_status == "full"
    assert ranked[1].match_status in {"partial", "ambiguous_or_mixed", "full_with_warnings"}


def test_crohns_only_partial_match_ranks_below_exact_uc_match():
    mappings = _uc_colon_rna_human_mappings()
    exact = _candidate("GSE334803")
    crohns_only = _candidate(
        "E-GEOD-57945",
        title="RNA-seq of treatment-naive pediatric patients with Crohn's disease",
        description="Homo sapiens transcriptome profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq of treatment-naive pediatric patients with Crohn's disease",
            "summary": "Homo sapiens transcriptome profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([crohns_only, exact], mappings),
        mappings,
    )

    assert ranked[0].accession == "GSE334803"
    assert ranked[1].accession == "E-GEOD-57945"
    assert ranked[1].match_status == "partial"


def test_rna_seq_requested_ranks_above_microarray_study():
    mappings = _uc_colon_rna_human_mappings()
    rnaseq = _candidate("GSE111111")
    microarray = _candidate(
        "E-GEOD-65114",
        title="Microarray analysis of colonic mucosal biopsies from ulcerative colitis patients",
        description="Homo sapiens expression profiling by array",
        metadata_fields={
            "title": "Microarray analysis of colonic mucosal biopsies from ulcerative colitis patients",
            "summary": "Homo sapiens expression profiling by array",
            "gdstype": "Expression profiling by array",
            "taxon": "Homo sapiens",
        },
    )

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([microarray, rnaseq], mappings),
        mappings,
    )

    assert ranked[0].accession == "GSE111111"
    assert ranked[1].accession == "E-GEOD-65114"


def test_direct_tissue_ranks_above_organoid_derived_model():
    mappings = _uc_colon_rna_human_mappings()
    direct = _candidate("GSE334803")
    organoid = _candidate(
        "GSE288517",
        title="Paired transcriptomics in cytokine-stimulated colon organoids from ulcerative colitis patients",
        description="RNA-seq of colon organoids from ulcerative colitis patients",
        metadata_fields={
            "title": "Paired transcriptomics in cytokine-stimulated colon organoids from ulcerative colitis patients",
            "summary": "RNA-seq of colon organoids from ulcerative colitis patients",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([organoid, direct], mappings),
        mappings,
    )

    assert ranked[0].accession == "GSE334803"
    assert ranked[0].match_status == "full"
    assert ranked[1].match_status == "ambiguous_or_mixed"


def test_integrated_results_sort_by_display_rank_score():
    mappings = _uc_colon_rna_human_mappings()
    full = _candidate("GSEFULL")
    ambiguous_high_relevance = _candidate(
        "GSE311230",
        title="Paired transcriptomics in cytokine-stimulated colon organoids from ulcerative colitis patients",
        description="RNA-seq of colon organoids from UC patients",
        metadata_fields={
            "title": "Paired transcriptomics in cytokine-stimulated colon organoids from ulcerative colitis patients",
            "summary": "RNA-seq of colon organoids from UC patients",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    partial_low_relevance = _candidate(
        "GSEPARTIAL",
        title="RNA-seq study at UC Berkeley",
        description="Expression profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq study at UC Berkeley",
            "summary": "Expression profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates(
            [ambiguous_high_relevance, partial_low_relevance, full],
            mappings,
        ),
        mappings,
    )

    display_scores = [candidate.score for candidate in ranked]
    assert display_scores == sorted(display_scores, reverse=True)
    assert ranked[0].match_status == "full"
    assert ranked[1].match_status == "partial"
    assert ranked[2].match_status == "ambiguous_or_mixed"
    assert ranked[2].score_breakdown.evidence_score > ranked[1].score_breakdown.evidence_score
    assert ranked[1].score > ranked[2].score
    assert ranked[1].score_breakdown.rank_tier >= 2.2
    assert ranked[2].score_breakdown.rank_tier == 1.0


def test_partial_matches_remain_in_ranked_results():
    mappings = _uc_colon_rna_human_mappings()
    partial = _candidate(
        "GSEPARTIAL",
        title="RNA-seq study at UC Berkeley",
        description="Expression profiling by high throughput sequencing",
        metadata_fields={
            "title": "RNA-seq study at UC Berkeley",
            "summary": "Expression profiling by high throughput sequencing",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    full = _candidate("GSEFULL")

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([partial, full], mappings),
        mappings,
    )

    assert len(ranked) == 2
    assert {item.match_status for item in ranked} == {"full", "partial"}


def test_alzheimers_brain_rnaseq_ranks_above_proteomics():
    mappings = [
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
    rnaseq_brain = DatasetCandidate(
        repository="GEO",
        accession="GSE310780",
        title="Amyloid-beta aggregates in brain endothelial cells in Alzheimer disease",
        description="Homo sapiens RNA-seq of brain tissue",
        metadata_fields={
            "title": "Amyloid-beta aggregates in brain endothelial cells in Alzheimer disease",
            "summary": "Homo sapiens RNA-seq of brain tissue",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
    )
    proteomics = DatasetCandidate(
        repository="Expression Atlas",
        accession="E-PROT-39",
        title="Proteomics of brain proteome in Alzheimer disease",
        description="Proteomics of brain proteome in Alzheimer disease",
        metadata_fields={
            "title": "Proteomics of brain proteome in Alzheimer disease",
            "summary": "Proteomics of brain proteome in Alzheimer disease",
            "taxon": "Homo sapiens",
        },
    )

    ranked = rank_annotated_candidates(
        annotate_dataset_candidates([proteomics, rnaseq_brain], mappings),
        mappings,
    )

    assert ranked[0].accession == "GSE310780"
    assert ranked[1].accession == "E-PROT-39"
