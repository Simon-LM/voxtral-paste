"""Unit tests for _select_models() — 3-tier routing logic."""

import importlib
import sys

import pytest


def _load_refine(monkeypatch, short=80, long=200):
    """Reload refine module with custom thresholds via env vars."""
    monkeypatch.setenv("REFINE_MODEL_THRESHOLD_SHORT", str(short))
    monkeypatch.setenv("REFINE_MODEL_THRESHOLD_LONG", str(long))
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    if "src.refine" in sys.modules:
        del sys.modules["src.refine"]
    import src.refine as refine
    return refine


class TestSelectModelsDefaultThresholds:
    def test_zero_words_is_short(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, fallback = refine._select_models(0)
        assert primary == refine._MODEL_SHORT
        assert fallback == refine._MODEL_SHORT_FALLBACK

    def test_one_word_is_short(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, _ = refine._select_models(1)
        assert primary == refine._MODEL_SHORT

    def test_just_below_short_threshold(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, _ = refine._select_models(refine._THRESHOLD_SHORT - 1)
        assert primary == refine._MODEL_SHORT

    def test_at_short_threshold_is_medium(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, fallback = refine._select_models(refine._THRESHOLD_SHORT)
        assert primary == refine._MODEL_MEDIUM
        assert fallback == refine._MODEL_MEDIUM_FALLBACK

    def test_mid_range_is_medium(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, _ = refine._select_models(100)
        assert primary == refine._MODEL_MEDIUM

    def test_just_below_long_threshold(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, _ = refine._select_models(refine._THRESHOLD_LONG - 1)
        assert primary == refine._MODEL_MEDIUM

    def test_at_long_threshold_is_long(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, fallback = refine._select_models(refine._THRESHOLD_LONG)
        assert primary == refine._MODEL_LONG
        assert fallback == refine._MODEL_LONG_FALLBACK

    def test_large_count_is_long(self, monkeypatch):
        refine = _load_refine(monkeypatch)
        primary, _ = refine._select_models(1000)
        assert primary == refine._MODEL_LONG


class TestSelectModelsCustomThresholds:
    def test_custom_thresholds_respected(self, monkeypatch):
        refine = _load_refine(monkeypatch, short=10, long=50)
        assert refine._THRESHOLD_SHORT == 10
        assert refine._THRESHOLD_LONG == 50

        primary_short, _ = refine._select_models(5)
        assert primary_short == refine._MODEL_SHORT

        primary_medium, _ = refine._select_models(25)
        assert primary_medium == refine._MODEL_MEDIUM

        primary_long, _ = refine._select_models(100)
        assert primary_long == refine._MODEL_LONG
