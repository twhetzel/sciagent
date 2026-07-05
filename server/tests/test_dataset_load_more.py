"""Tests for dataset-discovery load more."""

from __future__ import annotations

from unittest.mock import patch

from agent.dataset_discovery import load_more_dataset_search
from domain.dataset_search import ConceptMapping, DatasetCandidate, DatasetSearchCursor, InterpretedQuery


def _cursor() -> DatasetSearchCursor:
    mappings = [
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
            slot="assay",
            query_term="RNA-seq",
            curie="OBI:0002117",
            label="RNA-seq",
            ontology="OBI",
            synonyms=["RNA-seq"],
            source="curated",
        ),
    ]
    return DatasetSearchCursor(
        query="Find RNA-seq datasets for ulcerative colitis",
        interpreted_query=InterpretedQuery(disease="ulcerative colitis", assay="RNA-seq"),
        concept_mappings=mappings,
        strategy_offsets={"strict": 15},
        strategy_totals={"strict": 129, "broad_1": 175},
        seen_ids=["1"],
        seen_accessions=["GSEOLD"],
        total_found=175,
        primary_total_found=129,
        max_results=15,
        search_term="strict term",
        has_more=True,
    )


def _existing_candidate() -> DatasetCandidate:
    return DatasetCandidate(
        repository="GEO",
        accession="GSEOLD",
        title="Existing dataset",
        description="Homo sapiens RNA-seq of ulcerative colitis",
        metadata_fields={
            "title": "Existing dataset",
            "summary": "Homo sapiens RNA-seq of ulcerative colitis",
            "gdstype": "Expression profiling by high throughput sequencing",
            "taxon": "Homo sapiens",
        },
        score=0.9,
        match_status="full",
    )


def test_load_more_merges_and_reranks_candidates():
    more_payload = {
        "records": [
            {
                "uid": "2",
                "accession": "GSENEW",
                "title": "New dataset",
                "summary": "Homo sapiens RNA-seq of ulcerative colitis colon",
                "taxon": "Homo sapiens",
                "gdstype": "Expression profiling by high throughput sequencing",
                "_retrieval_strategy": "strict",
                "_retrieval_search_term": "strict term",
            }
        ],
        "added_count": 1,
        "has_more": True,
        "load_more_cursor": _cursor().model_copy(
            update={"seen_accessions": ["GSEOLD", "GSENEW"], "strategy_offsets": {"strict": 30}}
        ).model_dump(),
        "source": "NCBI GEO",
        "repository": "GEO",
    }

    with patch(
        "agent.dataset_discovery.fetch_more_repository_records",
        return_value=more_payload,
    ):
        result = load_more_dataset_search(_cursor(), [_existing_candidate()])

    accessions = [candidate.accession for candidate in result.candidates]
    assert "GSEOLD" in accessions
    assert "GSENEW" in accessions
    assert result.retrieved_count == 2
    assert result.has_more is True
    assert result.load_more_cursor is not None
    assert result.load_more_cursor.seen_accessions == ["GSEOLD", "GSENEW"]


def test_load_more_merges_and_reranks_immport_candidates():
    from domain.dataset_search import DatasetSearchCursor, InterpretedQuery
    from tools.immport_dataset_search import IMMPORT_REPOSITORY

    cursor = DatasetSearchCursor(
        query="Find public immunology datasets for asthma PBMC flow cytometry.",
        interpreted_query=InterpretedQuery(
            disease="asthma",
            tissue="PBMC",
            assay="Flow Cytometry",
            organism="human",
        ),
        concept_mappings=[],
        strategy_offsets={"strict": 2, "broad_1": 1, "broad_2": 1, "broad_3": 1},
        strategy_totals={"strict": 1, "broad_1": 4, "broad_2": 12, "broad_3": 28},
        seen_accessions=["SDYOLD"],
        total_found=28,
        primary_total_found=1,
        max_results=5,
        search_term="asthma Flow Cytometry PBMC",
        has_more=True,
    )

    existing = DatasetCandidate(
        repository=IMMPORT_REPOSITORY,
        accession="SDYOLD",
        title="Existing asthma study",
        description="Asthma PBMC flow cytometry",
        metadata_fields={"title": "Existing asthma study"},
        score=0.9,
        match_status="full",
    )

    more_payload = {
        "records": [
            {
                "accession": "SDYNEW",
                "title": "New asthma study",
                "description": "Asthma PBMC flow cytometry follow-up",
                "summary": "Asthma PBMC flow cytometry follow-up",
                "condition_or_disease": "asthma",
                "biosample_type": "PBMC",
                "assay_method": "Flow Cytometry",
                "species": "Homo sapiens",
                "url": "https://www.immport.org/shared/study/SDYNEW",
                "_retrieval_strategy": "broad_3",
                "_retrieval_search_term": "asthma",
            }
        ],
        "added_count": 1,
        "has_more": True,
        "load_more_cursor": cursor.model_copy(
            update={"seen_accessions": ["SDYOLD", "SDYNEW"], "strategy_offsets": {"broad_3": 6}}
        ).model_dump(),
        "source": "ImmPort",
        "repository": IMMPORT_REPOSITORY,
    }

    with patch(
        "agent.dataset_discovery.fetch_more_repository_records",
        return_value=more_payload,
    ):
        result = load_more_dataset_search(cursor, [existing])

    accessions = [candidate.accession for candidate in result.candidates]
    assert "SDYOLD" in accessions
    assert "SDYNEW" in accessions
    assert result.retrieved_count == 2
    assert result.has_more is True
    assert result.load_more_cursor is not None
