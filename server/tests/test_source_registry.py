"""Tests for NIAID-aligned source registry and /api/config."""

from domain.source_registry import (
    IMMPORT_SOURCE_ID,
    OMICSDI_SOURCE_ID,
    PLANNED_CONNECTOR_NOTE,
    SOURCE_REGISTRY,
    VDJSERVER_SOURCE_ID,
    VIVLI_SOURCE_ID,
)
from sciagent_server.config import (
    build_api_config,
    default_include_text_broad,
    is_source_enabled,
    resolve_dataset_search_options,
)


def test_source_registry_contains_niaid_entries():
    assert set(SOURCE_REGISTRY) == {
        IMMPORT_SOURCE_ID,
        OMICSDI_SOURCE_ID,
        VDJSERVER_SOURCE_ID,
        VIVLI_SOURCE_ID,
    }
    assert SOURCE_REGISTRY[IMMPORT_SOURCE_ID].implemented is True
    assert SOURCE_REGISTRY[VIVLI_SOURCE_ID].implemented is True
    assert SOURCE_REGISTRY[OMICSDI_SOURCE_ID].implemented is False


def test_build_api_config_marks_planned_sources_unavailable_by_default():
    config = build_api_config()
    by_id = {item["id"]: item for item in config["sources"]}

    assert by_id[IMMPORT_SOURCE_ID]["enabled_by_default"] is True
    assert by_id[IMMPORT_SOURCE_ID]["implemented"] is True
    assert by_id[IMMPORT_SOURCE_ID]["enabled"] is is_source_enabled(IMMPORT_SOURCE_ID)

    for source_id in (OMICSDI_SOURCE_ID, VDJSERVER_SOURCE_ID):
        item = by_id[source_id]
        assert item["implemented"] is False
        assert item["enabled"] is False
        assert item["enabled_by_default"] is False
        assert item["note"] == PLANNED_CONNECTOR_NOTE

    vivli = by_id[VIVLI_SOURCE_ID]
    assert vivli["implemented"] is True
    assert vivli["enabled"] is is_source_enabled(VIVLI_SOURCE_ID)
    assert vivli["enabled_by_default"] is True
    assert "note" not in vivli


def test_build_api_config_includes_registry_metadata():
    config = build_api_config()
    immport = next(item for item in config["sources"] if item["id"] == IMMPORT_SOURCE_ID)

    assert immport["display_name"] == "ImmPort"
    assert immport["source_type"] == "dataset_repository"
    assert immport["domain"] == "immunology"
    assert immport["access_profile"] == "open_or_registered"


def test_build_api_config_exposes_dataset_search_defaults():
    config = build_api_config()
    assert "dataset_search_defaults" in config
    assert isinstance(config["dataset_search_defaults"]["include_text_broad"], bool)


def test_resolve_dataset_search_options_uses_request_override():
    options = resolve_dataset_search_options({"include_text_broad": False})
    assert options.include_text_broad is False


def test_default_include_text_broad_honors_env(monkeypatch):
    monkeypatch.setenv("SCIAGENT_IMMPORT_TEXT_BROAD", "false")
    assert default_include_text_broad() is False
