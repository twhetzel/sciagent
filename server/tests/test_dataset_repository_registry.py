"""Tests for the dataset repository registry."""

from domain.dataset_repository_registry import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    IMMPORT_REPOSITORY,
    get_repository_spec,
    pick_load_more_cursor,
    repository_supports_load_more,
    resolve_enabled_dataset_repositories,
    supported_repositories,
)


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
