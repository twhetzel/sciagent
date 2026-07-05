"""Tests for Expression Atlas dataset discovery pipeline."""

from unittest.mock import patch

from agent.dataset_discovery import GXA_REPOSITORY, run_dataset_discovery
from domain.dataset_search import ConceptMapping


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


MOCK_SEARCH_RESULT = {
    "search_term": "ulcerative colitis RNA-seq colon",
    "search_strategies": [
        {"strategy": "strict", "search_term": "ulcerative colitis RNA-seq colon", "total_found": 1, "retrieved": 1, "new_ids": 1},
        {"strategy": "broad_1", "search_term": "ulcerative colitis RNA-seq", "total_found": 3, "retrieved": 3, "new_ids": 2},
    ],
    "total_found": 3,
    "primary_total_found": 1,
    "max_results": 10,
    "records": [
        {
            "accession": "E-MTAB-7860",
            "title": "RNA-seq of biopsies, crypts and organoids of inflamed and non-inflamed biopsies of ulcerative colitis patients",
            "description": "RNA-seq of biopsies, crypts and organoids of inflamed and non-inflamed biopsies of ulcerative colitis patients",
            "species": "Homo sapiens",
            "experiment_type": "rnaseq_mrna_differential",
            "url": "https://www.ebi.ac.uk/gxa/experiments/E-MTAB-7860",
            "_retrieval_strategy": "strict",
            "_retrieval_search_term": "ulcerative colitis RNA-seq colon",
        },
        {
            "accession": "E-GEOD-57945",
            "title": "RNA-seq pediatric IBD cohort",
            "description": "RNA-seq pediatric IBD cohort",
            "species": "Homo sapiens",
            "experiment_type": "rnaseq_mrna_differential",
            "url": "https://www.ebi.ac.uk/gxa/experiments/E-GEOD-57945",
            "_retrieval_strategy": "broad_1",
            "_retrieval_search_term": "ulcerative colitis RNA-seq",
        },
    ],
    "source": "Expression Atlas",
    "repository": GXA_REPOSITORY,
    "has_more": False,
    "load_more_cursor": None,
}


def test_run_dataset_discovery_gxa_returns_ranked_candidates():
    query = "Find public RNA-seq datasets for ulcerative colitis colon tissue"

    with patch("agent.dataset_discovery.ground_interpreted_query", return_value=_uc_mappings()):
        with patch(
            "agent.dataset_discovery.fetch_repository_records",
            return_value=MOCK_SEARCH_RESULT,
        ):
            result = run_dataset_discovery(query, repository=GXA_REPOSITORY, max_results=10)

    assert result.repository == GXA_REPOSITORY
    assert len(result.candidates) == 2
    assert result.search_strategies
    assert result.candidates[0].accession == "E-MTAB-7860"
    assert result.candidates[0].repository == GXA_REPOSITORY
    assert any(c.evidence_snippets for c in result.candidates)
