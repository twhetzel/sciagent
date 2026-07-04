"""Tests for multi-repository dataset discovery merge and deduplication."""

from unittest.mock import patch

from agent.dataset_discovery import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    canonical_dataset_key,
    merge_repository_search_results,
    run_dataset_discovery,
)
from domain.dataset_search import ConceptMapping


def test_canonical_dataset_key_links_geo_and_gxa_accessions():
    assert canonical_dataset_key("GSE57945") == "GSE57945"
    assert canonical_dataset_key("E-GEOD-57945") == "GSE57945"
    assert canonical_dataset_key("E-MTAB-7860") == "E-MTAB-7860"


def test_merge_repository_search_results_dedupes_overlapping_studies():
    geo = {
        "repository": GEO_REPOSITORY,
        "source": "NCBI GEO",
        "search_term": "ulcerative colitis RNA-seq colon",
        "search_strategies": [
            {"strategy": "strict", "search_term": "ulcerative colitis RNA-seq colon", "total_found": 1, "retrieved": 1, "new_ids": 1},
        ],
        "total_found": 5,
        "primary_total_found": 1,
        "max_results": 10,
        "records": [
            {
                "accession": "GSE57945",
                "title": "GEO pediatric IBD cohort",
                "summary": "RNA-seq pediatric IBD cohort",
                "_retrieval_strategy": "strict",
            }
        ],
        "has_more": False,
    }
    gxa = {
        "repository": GXA_REPOSITORY,
        "source": "Expression Atlas",
        "search_term": "ulcerative colitis RNA-seq colon",
        "search_strategies": [
            {"strategy": "strict", "search_term": "ulcerative colitis RNA-seq colon", "total_found": 1, "retrieved": 1, "new_ids": 1},
        ],
        "total_found": 20,
        "primary_total_found": 1,
        "max_results": 10,
        "records": [
            {
                "accession": "E-GEOD-57945",
                "title": "GXA pediatric IBD cohort",
                "description": "RNA-seq pediatric IBD cohort",
                "_retrieval_strategy": "strict",
            },
            {
                "accession": "E-MTAB-7860",
                "title": "GXA UC biopsies",
                "description": "RNA-seq UC biopsies",
                "_retrieval_strategy": "strict",
            },
        ],
        "has_more": False,
    }

    merged = merge_repository_search_results([geo, gxa])

    assert merged["repository"] == "GEO + Expression Atlas"
    assert merged["source"] == "NCBI GEO, Expression Atlas"
    assert merged["total_found"] == 25
    assert len(merged["records"]) == 2
    accessions = {record["accession"] for record in merged["records"]}
    assert accessions == {"GSE57945", "E-MTAB-7860"}
    assert merged["records"][0]["accession"] == "GSE57945"
    assert merged["search_strategies"][0]["repository"] == GEO_REPOSITORY
    assert merged["search_strategies"][1]["repository"] == GXA_REPOSITORY


def _uc_mappings() -> list[ConceptMapping]:
    return [
        ConceptMapping(
            slot="disease",
            query_term="ulcerative colitis",
            curie="MONDO:0005101",
            label="ulcerative colitis",
            ontology="MONDO",
            match_type="exact",
            source="curated",
            confidence=0.95,
        ),
        ConceptMapping(
            slot="tissue",
            query_term="colon",
            curie="UBERON:0001155",
            label="colon",
            ontology="UBERON",
            match_type="exact",
            source="curated",
            confidence=0.95,
        ),
        ConceptMapping(
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0000630",
            label="RNA-seq",
            ontology="OBI",
            match_type="exact",
            source="curated",
            confidence=0.95,
        ),
    ]


def test_run_dataset_discovery_multi_repo_merges_and_ranks():
    query = "Find public RNA-seq datasets for ulcerative colitis colon tissue"
    geo_result = {
        "search_term": "ulcerative colitis RNA-seq colon",
        "search_strategies": [],
        "total_found": 5,
        "primary_total_found": 1,
        "max_results": 10,
        "records": [
            {
                "accession": "GSE57945",
                "title": "GEO pediatric IBD cohort",
                "summary": "RNA-seq pediatric IBD cohort colon ulcerative colitis",
            }
        ],
        "source": "NCBI GEO",
        "repository": GEO_REPOSITORY,
        "has_more": False,
    }
    gxa_result = {
        "search_term": "ulcerative colitis RNA-seq colon",
        "search_strategies": [],
        "total_found": 20,
        "primary_total_found": 1,
        "max_results": 10,
        "records": [
            {
                "accession": "E-GEOD-57945",
                "title": "GXA pediatric IBD cohort",
                "description": "RNA-seq pediatric IBD cohort",
            },
            {
                "accession": "E-MTAB-7860",
                "title": "GXA UC biopsies",
                "description": "RNA-seq UC biopsies colon ulcerative colitis",
                "species": "Homo sapiens",
                "experiment_type": "rnaseq_mrna_differential",
                "url": "https://www.ebi.ac.uk/gxa/experiments/E-MTAB-7860",
            },
        ],
        "source": "Expression Atlas",
        "repository": GXA_REPOSITORY,
        "has_more": False,
    }

    with patch("agent.dataset_discovery.ground_interpreted_query", return_value=_uc_mappings()):
        with patch("agent.dataset_discovery.search_repository", side_effect=[geo_result, gxa_result]):
            result = run_dataset_discovery(
                query,
                repository=[GEO_REPOSITORY, GXA_REPOSITORY],
                max_results=10,
            )

    assert result.repository == "GEO + Expression Atlas"
    assert len(result.candidates) == 2
    accessions = {candidate.accession for candidate in result.candidates}
    assert accessions == {"GSE57945", "E-MTAB-7860"}
