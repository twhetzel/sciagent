"""Tests for GEO_MAX_RESULTS configuration."""

from __future__ import annotations

import os

from tools.geo_dataset_search import (
    DEFAULT_GEO_MAX_RESULTS,
    GEO_MAX_RESULTS_CAP,
    get_geo_max_results,
)


def test_get_geo_max_results_default(monkeypatch):
    monkeypatch.delenv("GEO_MAX_RESULTS", raising=False)
    assert get_geo_max_results() == DEFAULT_GEO_MAX_RESULTS


def test_get_geo_max_results_from_env(monkeypatch):
    monkeypatch.setenv("GEO_MAX_RESULTS", "50")
    assert get_geo_max_results() == 50


def test_get_geo_max_results_clamps_high_values(monkeypatch):
    monkeypatch.setenv("GEO_MAX_RESULTS", "9999")
    assert get_geo_max_results() == GEO_MAX_RESULTS_CAP


def test_get_geo_max_results_override_beats_env(monkeypatch):
    monkeypatch.setenv("GEO_MAX_RESULTS", "50")
    assert get_geo_max_results(25) == 25


def test_get_geo_max_results_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("GEO_MAX_RESULTS", "not-a-number")
    assert get_geo_max_results() == DEFAULT_GEO_MAX_RESULTS
