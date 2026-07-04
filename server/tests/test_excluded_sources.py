"""Tests for SCIAGENT_EXCLUDED_SOURCES and SCIAGENT_EXCLUDED_TOOLS blocklists."""

from unittest.mock import patch

from agent.orchestrator import AgentOrchestrator
from agent.registry import ToolRegistry
from sciagent_server.config import (
    is_agent_tool_enabled,
    is_capability_enabled,
    is_source_enabled,
    parse_excluded_sources,
    parse_excluded_tools,
)


def test_parse_excluded_sources_returns_empty_when_unset():
    assert parse_excluded_sources("") == set()


def test_parse_excluded_tools_returns_empty_when_unset():
    assert parse_excluded_tools("") == set()


def test_is_source_enabled_respects_source_blocklist_only():
    with patch("sciagent_server.config.EXCLUDED_SOURCES", {"openalex"}):
        with patch("sciagent_server.config.EXCLUDED_TOOLS", set()):
            assert is_source_enabled("pubmed") is True
            assert is_source_enabled("openalex") is False
            assert is_agent_tool_enabled("summarize") is True


def test_is_agent_tool_enabled_respects_tool_blocklist_only():
    with patch("sciagent_server.config.EXCLUDED_SOURCES", set()):
        with patch("sciagent_server.config.EXCLUDED_TOOLS", {"summarize"}):
            assert is_agent_tool_enabled("summarize") is False
            assert is_source_enabled("pubmed") is True


def test_summarize_in_excluded_sources_does_not_disable_summarize():
    with patch("sciagent_server.config.EXCLUDED_SOURCES", {"summarize"}):
        with patch("sciagent_server.config.EXCLUDED_TOOLS", set()):
            assert is_capability_enabled("summarize") is True


def test_registry_skips_excluded_sources_and_tools():
    with patch(
        "agent.registry.is_capability_enabled",
        side_effect=lambda name: name not in {"openalex", "summarize", "geo_dataset_search"},
    ):
        registry = ToolRegistry()

    names = {tool["name"] for tool in registry.list_tools()}
    assert "openalex" not in names
    assert "summarize" not in names
    assert "geo_dataset_search" not in names
    assert "pubmed" in names


def test_orchestrator_filters_planned_capabilities_to_registered_items():
    with patch(
        "agent.registry.is_capability_enabled",
        side_effect=lambda name: name in {"mygene", "uniprot"},
    ):
        orchestrator = AgentOrchestrator()
        plan = orchestrator._filter_planned_tools(orchestrator._plan("BRCA1 gene"))

    assert plan["tools_needed"] == ["mygene", "uniprot"]


def test_build_expression_atlas_params_uses_interpreted_query():
    orchestrator = AgentOrchestrator()
    params = orchestrator._build_expression_atlas_params(
        "Find public RNA-seq datasets for ulcerative colitis colon tissue"
    )

    assert params["interpreted_query"]["disease"] == "ulcerative colitis"
    assert params["interpreted_query"]["tissue"] == "colon"
    assert params["interpreted_query"]["assay"] == "RNA-seq"
    assert params["species"] == "Homo sapiens"


def test_dataset_discovery_routes_to_gxa_when_geo_excluded():
    with patch(
        "agent.registry.is_capability_enabled",
        side_effect=lambda name: name != "geo_dataset_search",
    ):
        with patch("agent.orchestrator.AgentOrchestrator._run_dataset_discovery") as run_discovery:
            run_discovery.return_value = ("summary", [{"id": "agent_run"}], {"repository": "Expression Atlas"})
            orchestrator = AgentOrchestrator()
            orchestrator.run("Find public RNA-seq datasets for ulcerative colitis colon tissue")

    run_discovery.assert_called_once()
    assert run_discovery.call_args.kwargs["repositories"] == ["Expression Atlas"]
