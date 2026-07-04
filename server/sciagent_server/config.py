"""Environment-based configuration for SciAgent Studio server."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

API_VERSION = "0.1.0"

HOST = os.environ.get("SCIAGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("SCIAGENT_PORT", "8000"))
WORKERS = int(os.environ.get("SCIAGENT_WORKERS", "1"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "SCIAGENT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://localhost:8080",
    ).split(",")
    if origin.strip()
]

# External scientific databases/APIs (shown as "Resources" in the UI).
SOURCE_NAMES = frozenset({
    "pubmed",
    "openalex",
    "europepmc",
    "expression_atlas",
    "mygene",
    "uniprot",
    "clinvar",
    "alphafold",
    "geo_dataset_search",
})

# Agent capabilities that are not external data sources.
AGENT_TOOL_NAMES = frozenset({
    "summarize",
})


def _parse_name_list(raw: str | None, env_var: str) -> set[str]:
    if raw is None:
        raw = os.environ.get(env_var, "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def parse_excluded_sources(raw: str | None = None) -> set[str]:
    """Parse SCIAGENT_EXCLUDED_SOURCES; empty set means no sources are excluded."""
    return _parse_name_list(raw, "SCIAGENT_EXCLUDED_SOURCES")


def parse_excluded_tools(raw: str | None = None) -> set[str]:
    """Parse SCIAGENT_EXCLUDED_TOOLS; empty set means no agent tools are excluded."""
    return _parse_name_list(raw, "SCIAGENT_EXCLUDED_TOOLS")


EXCLUDED_SOURCES = parse_excluded_sources()
EXCLUDED_TOOLS = parse_excluded_tools()


def is_source_enabled(name: str) -> bool:
    """Return True when an external source is not listed in SCIAGENT_EXCLUDED_SOURCES."""
    if name not in SOURCE_NAMES:
        return True
    return name not in EXCLUDED_SOURCES


def is_agent_tool_enabled(name: str) -> bool:
    """Return True when an agent tool is not listed in SCIAGENT_EXCLUDED_TOOLS."""
    if name not in AGENT_TOOL_NAMES:
        return True
    return name not in EXCLUDED_TOOLS


def is_capability_enabled(name: str) -> bool:
    """Return True when a registered source or agent tool should be available."""
    if name in SOURCE_NAMES:
        return is_source_enabled(name)
    if name in AGENT_TOOL_NAMES:
        return is_agent_tool_enabled(name)
    return True


def get_ncbi_email() -> str:
    """Return NCBI E-utilities contact email (NCBI_EMAIL, else legacy PUBMED_EMAIL)."""
    return (
        os.environ.get("NCBI_EMAIL", "").strip()
        or os.environ.get("PUBMED_EMAIL", "").strip()
    )


def get_ncbi_api_key() -> str:
    """Return optional NCBI E-utilities API key for higher rate limits."""
    return os.environ.get("NCBI_API_KEY", "").strip()


def get_ncbi_tool_name() -> str:
    """Return NCBI E-utilities tool name (PUBMED_TOOL for backwards compatibility)."""
    return os.environ.get("PUBMED_TOOL", "sciagent_studio").strip() or "sciagent_studio"


def build_ncbi_params() -> dict[str, str]:
    """Return shared NCBI E-utilities query parameters (tool, email, optional api_key)."""
    params = {
        "tool": get_ncbi_tool_name(),
        "email": get_ncbi_email(),
    }
    api_key = get_ncbi_api_key()
    if api_key:
        params["api_key"] = api_key
    return params
