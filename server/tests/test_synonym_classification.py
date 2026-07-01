"""Tests for synonym classification in GEO dataset discovery."""

from __future__ import annotations

from domain.dataset_search import ConceptMapping
from domain.evidence_extraction import extract_evidence_for_mapping
from domain.ontology_grounding import build_geo_search_term
from domain.synonym_classification import (
    build_aliases_for_mapping,
    retrieval_terms_for_mapping,
    terms_matching_in_text,
)


def _ulcerative_colitis_mapping() -> ConceptMapping:
    return ConceptMapping(
        slot="disease",
        query_term="ulcerative colitis",
        curie="MONDO:0005101",
        label="ulcerative colitis",
        ontology="MONDO",
        synonyms=["ulcerative colitis", "UC", "colitis ulcerative"],
        source="curated",
    )


def test_uc_excluded_from_broad_geo_retrieval_query():
    mapping = _ulcerative_colitis_mapping()
    retrieval_terms = retrieval_terms_for_mapping(mapping)
    search_term = build_geo_search_term([mapping])

    assert "uc" not in retrieval_terms
    assert " UC " not in f" {search_term} "
    assert "uc OR" not in search_term.lower()
    assert "ulcerative colitis" in retrieval_terms
    assert "colitis ulcerative" in retrieval_terms


def test_uc_alias_marked_contextual_and_unsafe_for_retrieval():
    mapping = _ulcerative_colitis_mapping()
    aliases = build_aliases_for_mapping(mapping)
    uc_alias = next(alias for alias in aliases if alias.term == "UC")

    assert uc_alias.category == "acronym"
    assert uc_alias.safe_for_retrieval is False
    assert uc_alias.requires_context is True


def test_uc_counted_with_supporting_context():
    mapping = _ulcerative_colitis_mapping()
    fields = {"title": "Gene expression in ulcerative colitis (UC) patients", "summary": ""}

    assert terms_matching_in_text(mapping, fields["title"])
    supported, snippets = extract_evidence_for_mapping(mapping, fields)
    assert supported
    assert snippets


def test_uc_counted_with_colitis_context():
    mapping = _ulcerative_colitis_mapping()
    fields = {"title": "UC patients with colitis", "summary": ""}

    assert terms_matching_in_text(mapping, fields["title"])
    supported, _ = extract_evidence_for_mapping(mapping, fields)
    assert supported


def test_uc_not_counted_for_unrelated_usage():
    mapping = _ulcerative_colitis_mapping()
    fields = {"title": "Spatial transcriptomics at UC Berkeley", "summary": ""}

    assert not terms_matching_in_text(mapping, fields["title"])
    supported, snippets = extract_evidence_for_mapping(mapping, fields)
    assert not supported
    assert not snippets


def test_multi_word_synonyms_remain_in_retrieval():
    mapping = _ulcerative_colitis_mapping()
    retrieval_terms = retrieval_terms_for_mapping(mapping)
    search_term = build_geo_search_term([mapping])

    assert "colitis ulcerative" in retrieval_terms
    assert '"colitis ulcerative"' in search_term or "colitis ulcerative" in search_term
