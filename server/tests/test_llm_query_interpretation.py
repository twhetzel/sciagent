"""Tests for optional LLM interpret fallback."""

from unittest.mock import patch

from domain.dataset_search import ConceptMapping, InterpretedQuery
from domain.llm_query_interpretation import (
    is_llm_interpret_enabled,
    maybe_llm_interpret_query,
    should_run_llm_interpret,
)


def test_should_run_llm_interpret_when_core_slots_missing_and_key_set():
    interpreted = InterpretedQuery()
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "SCIAGENT_LLM_INTERPRET": "true"}):
        assert should_run_llm_interpret(
            "Find datasets for childhood wheezing in blood",
            interpreted,
        )


def test_should_not_run_when_rules_filled_core_slots():
    interpreted = InterpretedQuery(
        disease="asthma",
        tissue="PBMC",
        assay="Flow Cytometry",
        organism="human",
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        assert not should_run_llm_interpret("Find asthma PBMC flow cytometry datasets", interpreted)


def test_maybe_llm_interpret_query_validates_through_grounding():
    interpreted = InterpretedQuery()
    llm_payload = {
        "disease": "asthma",
        "tissue": "PBMC",
        "assay": "Flow Cytometry",
        "organism": "human",
    }
    mapping = ConceptMapping(
        slot="disease",
        query_term="asthma",
        curie="MONDO:0004979",
        label="asthma",
        ontology="MONDO",
        match_type="exact",
        source="ols",
        confidence=0.92,
    )

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch(
            "domain.llm_query_interpretation._extract_llm_facets",
            return_value=llm_payload,
        ):
            with patch(
                "domain.llm_query_interpretation.ground_term",
                return_value=[mapping],
            ):
                merged, trace = maybe_llm_interpret_query(
                    "Find public immunology datasets for childhood wheezing blood flow cytometry",
                    interpreted,
                )

    assert merged.disease == "asthma"
    assert trace is not None
    assert trace["status"] == "completed"
    assert "disease" in trace["filled_slots"]


def test_is_llm_interpret_disabled_by_env_flag():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "SCIAGENT_LLM_INTERPRET": "false"}):
        assert not is_llm_interpret_enabled()
