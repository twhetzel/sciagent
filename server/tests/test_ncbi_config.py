"""Tests for shared NCBI E-utilities configuration."""

from sciagent_server.config import build_ncbi_params, get_ncbi_api_key, get_ncbi_email


def test_get_ncbi_email_prefers_ncbi_email(monkeypatch):
    monkeypatch.setenv("NCBI_EMAIL", "ncbi@example.com")
    monkeypatch.setenv("PUBMED_EMAIL", "pubmed@example.com")
    assert get_ncbi_email() == "ncbi@example.com"


def test_get_ncbi_email_falls_back_to_pubmed_email(monkeypatch):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.setenv("PUBMED_EMAIL", "pubmed@example.com")
    assert get_ncbi_email() == "pubmed@example.com"


def test_build_ncbi_params_includes_api_key_when_set(monkeypatch):
    monkeypatch.setenv("NCBI_API_KEY", "secret-key")
    params = build_ncbi_params()
    assert params["api_key"] == "secret-key"


def test_get_ncbi_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("NCBI_API_KEY", "secret-key")
    assert get_ncbi_api_key() == "secret-key"
