"""Tests for NCBI E-utilities retry and throttling in GEO search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from tools import geo_dataset_search


@pytest.fixture(autouse=True)
def reset_ncbi_state():
    geo_dataset_search._last_ncbi_request_at = 0.0
    geo_dataset_search._ncbi_email_warning_logged = False
    yield
    geo_dataset_search._last_ncbi_request_at = 0.0
    geo_dataset_search._ncbi_email_warning_logged = False


def test_ncbi_get_retries_on_429_then_succeeds():
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    ok = MagicMock()
    ok.status_code = 200
    ok.raise_for_status = MagicMock()

    with patch("tools.geo_dataset_search.requests.get", side_effect=[rate_limited, ok]) as mock_get:
        with patch("tools.geo_dataset_search.time.sleep") as mock_sleep:
            response = geo_dataset_search._ncbi_get(
                "https://example.test/esummary.fcgi",
                {"db": "gds", "id": "1", "retmode": "json"},
            )

    assert response is ok
    assert mock_get.call_count == 2
    mock_sleep.assert_called()


def test_ncbi_get_raises_after_repeated_429():
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.raise_for_status.side_effect = requests.HTTPError("429 Client Error")

    with patch(
        "tools.geo_dataset_search.requests.get",
        return_value=rate_limited,
    ):
        with patch("tools.geo_dataset_search.time.sleep"):
            with pytest.raises(requests.HTTPError):
                geo_dataset_search._ncbi_get(
                    "https://example.test/esearch.fcgi",
                    {"db": "gds", "term": "test", "retmode": "json"},
                )


def test_ncbi_params_includes_api_key_when_set(monkeypatch):
    monkeypatch.setenv("NCBI_API_KEY", "test-key")
    params = geo_dataset_search._ncbi_params()
    assert params["api_key"] == "test-key"


def test_ncbi_params_prefers_ncbi_email_over_pubmed_fallback(monkeypatch):
    monkeypatch.setenv("NCBI_EMAIL", "ncbi@example.com")
    monkeypatch.setenv("PUBMED_EMAIL", "pubmed@example.com")
    params = geo_dataset_search._ncbi_params()
    assert params["email"] == "ncbi@example.com"


def test_ncbi_params_falls_back_to_pubmed_email(monkeypatch):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.setenv("PUBMED_EMAIL", "pubmed@example.com")
    params = geo_dataset_search._ncbi_params()
    assert params["email"] == "pubmed@example.com"
