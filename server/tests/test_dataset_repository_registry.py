"""Tests for the dataset repository registry."""

from domain.dataset_repository_registry import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    IMMPORT_REPOSITORY,
    OMICSDI_REPOSITORY,
    PROTEOMEXCHANGE_REPOSITORY,
    VDJSERVER_REPOSITORY,
    filter_repositories_for_interpreted_query,
    get_repository_spec,
    pick_load_more_cursor,
    repository_supports_load_more,
    resolve_enabled_dataset_repositories,
    supported_repositories,
)
from domain.dataset_search import InterpretedQuery


def test_supported_repositories_include_geo_gxa_immport():
    repos = supported_repositories()
    assert GEO_REPOSITORY in repos
    assert GXA_REPOSITORY in repos
    assert IMMPORT_REPOSITORY in repos


def test_load_more_support_flags():
    assert repository_supports_load_more(GEO_REPOSITORY) is True
    assert repository_supports_load_more(IMMPORT_REPOSITORY) is True
    assert repository_supports_load_more(GXA_REPOSITORY) is False


def test_pick_load_more_cursor_prefers_higher_priority_repo():
    cursor = {"query": "q", "repository": GEO_REPOSITORY, "interpreted_query": {}}
    merged = pick_load_more_cursor(
        [
            {
                "repository": IMMPORT_REPOSITORY,
                "has_more": True,
                "load_more_cursor": {"repository": IMMPORT_REPOSITORY},
            },
            {
                "repository": GEO_REPOSITORY,
                "has_more": True,
                "load_more_cursor": cursor,
            },
        ]
    )
    assert merged == cursor


def test_new_repository_spec_requires_tool_name_and_handlers():
    spec = get_repository_spec(GEO_REPOSITORY)
    assert spec.tool_name == "geo_dataset_search"
    assert spec.fetch_records is not None
    assert spec.fetch_more_records is not None
    assert spec.normalize_records is not None
    assert spec.resolve_max_results is not None


def test_resolve_enabled_dataset_repositories_respects_registry_and_priority():
    class FakeRegistry:
        def __init__(self, enabled: set[str]):
            self._enabled = enabled

        def get_tool(self, name: str):
            return object() if name in self._enabled else None

    all_enabled = resolve_enabled_dataset_repositories(
        FakeRegistry({"geo_dataset_search", "expression_atlas", "immport"})
    )
    assert all_enabled == [GEO_REPOSITORY, GXA_REPOSITORY, IMMPORT_REPOSITORY]

    without_geo = resolve_enabled_dataset_repositories(
        FakeRegistry({"expression_atlas", "immport"})
    )
    assert without_geo == [GXA_REPOSITORY, IMMPORT_REPOSITORY]


def test_filter_repositories_skips_proteomexchange_for_metabolomics():
    interpreted = InterpretedQuery(
        disease="inflammatory bowel disease",
        tissue="serum",
        assay="metabolomics",
        organism=None,
    )
    repos = [PROTEOMEXCHANGE_REPOSITORY, OMICSDI_REPOSITORY, GEO_REPOSITORY]
    filtered, skipped = filter_repositories_for_interpreted_query(
        repos,
        interpreted,
        query="Find public metabolomics datasets for inflammatory bowel disease serum.",
    )
    assert filtered == [OMICSDI_REPOSITORY, GEO_REPOSITORY]
    assert skipped == [PROTEOMEXCHANGE_REPOSITORY]


def test_filter_repositories_keeps_proteomexchange_for_proteomics():
    interpreted = InterpretedQuery(
        disease="asthma",
        tissue="lung",
        assay="proteomics",
        organism=None,
    )
    repos = [PROTEOMEXCHANGE_REPOSITORY, OMICSDI_REPOSITORY]
    filtered, skipped = filter_repositories_for_interpreted_query(repos, interpreted)
    assert filtered == repos
    assert skipped == []


def test_filter_repositories_skips_vdjserver_for_unrelated_assay_queries():
    interpreted = InterpretedQuery(
        disease="asthma",
        tissue="lung",
        assay="proteomics",
        organism=None,
    )
    repos = [VDJSERVER_REPOSITORY, OMICSDI_REPOSITORY, GEO_REPOSITORY]
    filtered, skipped = filter_repositories_for_interpreted_query(
        repos,
        interpreted,
        query="Find public proteomics datasets for asthma lung tissue.",
    )
    assert filtered == [OMICSDI_REPOSITORY, GEO_REPOSITORY]
    assert skipped == [VDJSERVER_REPOSITORY]


def test_filter_repositories_keeps_vdjserver_for_repertoire_queries():
    interpreted = InterpretedQuery(
        disease="COVID-19",
        tissue="blood",
        assay=None,
        organism=None,
    )
    repos = [VDJSERVER_REPOSITORY, IMMPORT_REPOSITORY]
    filtered, skipped = filter_repositories_for_interpreted_query(
        repos,
        interpreted,
        query="Find public BCR repertoire datasets for COVID-19 blood.",
    )
    assert filtered == repos
    assert skipped == []


def test_vdjserver_repository_spec_supports_load_more():
    spec = get_repository_spec(VDJSERVER_REPOSITORY)
    assert spec.tool_name == "vdjserver"
    assert spec.fetch_more_records is not None
    assert repository_supports_load_more(VDJSERVER_REPOSITORY) is True
