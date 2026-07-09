"""Tests for relaxed single-word disease/assay phrase grounding (Option B)."""

from unittest.mock import patch

from domain.dataset_search import ConceptMapping, InterpretedQuery
from domain.facet_phrase_resolution import resolve_phrase_facets


def test_single_word_disease_phrase_can_use_dynamic_grounding():
    interpreted = InterpretedQuery()
    mapping = ConceptMapping(
        slot="disease",
        query_term="lupus",
        curie="MONDO:0007915",
        label="systemic lupus erythematosus",
        ontology="MONDO",
        match_type="exact",
        source="ols",
        confidence=0.92,
    )

    with patch(
        "domain.facet_phrase_resolution.ground_phrase_variants",
        return_value=([mapping], True),
    ):
        result = resolve_phrase_facets("Find datasets for lupus kidney tissue", interpreted)

    assert result.disease == "systemic lupus erythematosus"
