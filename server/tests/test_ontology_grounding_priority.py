"""Tests for facet-aware ontology priority during grounding."""

from __future__ import annotations

from domain.dataset_search import ConceptMapping, InterpretedQuery
from domain.ontology_grounder import OntologyGrounder
from domain.ontology_providers.base import (
    merge_concept_candidates,
    select_concept_with_debug,
)
from domain.ontology_providers.curated import CuratedAliasProvider


def _hp_crohns_ols() -> ConceptMapping:
    return ConceptMapping(
        slot="disease",
        query_term="Crohn's disease",
        curie="HP:0100280",
        label="Crohn's disease",
        ontology="HP",
        match_type="exact",
        source="ols",
        confidence=0.92,
        explanation="OLS exact match",
    )


def _mondo_alzheimer_ols() -> ConceptMapping:
    return ConceptMapping(
        slot="disease",
        query_term="Alzheimer disease",
        curie="MONDO:0004975",
        label="Alzheimer disease",
        ontology="MONDO",
        match_type="exact",
        source="ols",
        confidence=0.92,
        explanation="OLS exact match",
    )


class _StaticProvider:
    def __init__(self, name: str, candidates: list[ConceptMapping]) -> None:
        self.name = name
        self._candidates = candidates

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        return [
            candidate.model_copy(update={"slot": slot, "query_term": term})
            for candidate in self._candidates
            if candidate.slot == slot or candidate.slot == "disease"
        ]


def test_disease_prefers_mondo_over_hpo_when_both_available():
    ranked = merge_concept_candidates(
        [_hp_crohns_ols(), CuratedAliasProvider().lookup("disease", "Crohn's disease")[0]],
        slot="disease",
    )
    selected = select_concept_with_debug(ranked, slot="disease")

    assert selected is not None
    assert selected.curie == "MONDO:0005011"
    assert selected.ontology == "MONDO"
    assert any(item["curie"] == "HP:0100280" for item in selected.rejected_candidates)
    assert "primary ontology tier" in selected.selection_reason


def test_crohns_grounds_to_mondo_not_hpo_with_mocked_providers():
    grounder = OntologyGrounder(
        [
            _StaticProvider("ols", [_hp_crohns_ols()]),
            CuratedAliasProvider(),
        ]
    )
    interpreted = InterpretedQuery(disease="Crohn's disease")
    mappings = grounder.ground_interpreted_query(interpreted)

    assert len(mappings) == 1
    assert mappings[0].curie == "MONDO:0005011"
    assert mappings[0].ontology == "MONDO"
    assert mappings[0].rejected_candidates


def test_alzheimer_stays_on_mondo_when_mondo_candidate_exists():
    grounder = OntologyGrounder([_StaticProvider("ols", [_mondo_alzheimer_ols()])])
    interpreted = InterpretedQuery(disease="Alzheimer disease")
    mappings = grounder.ground_interpreted_query(interpreted)

    assert mappings[0].curie == "MONDO:0004975"
    assert mappings[0].ontology == "MONDO"


def test_ulcerative_colitis_stays_on_mondo():
    grounder = OntologyGrounder([CuratedAliasProvider()])
    interpreted = InterpretedQuery(disease="ulcerative colitis")
    mappings = grounder.ground_interpreted_query(interpreted)

    assert mappings[0].curie == "MONDO:0005101"
    assert mappings[0].ontology == "MONDO"


def test_disease_uses_hpo_only_when_no_mondo_or_efo_available():
    selected = select_concept_with_debug([_hp_crohns_ols()], slot="disease")

    assert selected is not None
    assert selected.curie == "HP:0100280"
    assert "fallback ontology tier" in selected.selection_reason
    assert selected.rejected_candidates == []


def test_phenotype_prefers_hpo_over_mondo():
    mondo_candidate = ConceptMapping(
        slot="phenotype",
        query_term="seizure",
        curie="MONDO:0000077",
        label="seizure",
        ontology="MONDO",
        match_type="exact",
        source="ols",
        confidence=0.92,
    )
    hpo_candidate = ConceptMapping(
        slot="phenotype",
        query_term="seizure",
        curie="HP:0001250",
        label="Seizure",
        ontology="HP",
        match_type="exact",
        source="ols",
        confidence=0.86,
    )

    selected = select_concept_with_debug(
        [mondo_candidate, hpo_candidate],
        slot="phenotype",
    )

    assert selected is not None
    assert selected.curie == "HP:0001250"
    assert any(item["curie"] == "MONDO:0000077" for item in selected.rejected_candidates)
