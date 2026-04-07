"""Unit tests for history injection strategy per refinement tier.

Covers:
- _load_history() with max_bullets cap
- History injection per tier (short=none, medium=capped, long=full)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _get_refine(monkeypatch, *, enable_history=True, inject_medium=40):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("ENABLE_HISTORY", "true" if enable_history else "false")
    monkeypatch.setenv("HISTORY_INJECT_BULLETS_MEDIUM", str(inject_medium))
    if "src.refine" in sys.modules:
        del sys.modules["src.refine"]
    import src.refine as refine
    return refine


class TestLoadHistoryCap:
    def test_no_cap_returns_all(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        bullets = "\n".join(f"- bullet {i}" for i in range(10))
        history_file = tmp_path / "history.txt"
        history_file.write_text(bullets)
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        result = refine._load_history()
        assert result.count("- bullet") == 10

    def test_cap_returns_last_n(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        bullets = "\n".join(f"- bullet {i}" for i in range(10))
        history_file = tmp_path / "history.txt"
        history_file.write_text(bullets)
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        result = refine._load_history(max_bullets=3)
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 3
        assert "bullet 7" in result
        assert "bullet 8" in result
        assert "bullet 9" in result
        assert "bullet 0" not in result

    def test_cap_larger_than_file_returns_all(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        bullets = "\n".join(f"- bullet {i}" for i in range(5))
        history_file = tmp_path / "history.txt"
        history_file.write_text(bullets)
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        result = refine._load_history(max_bullets=100)
        assert result.count("- bullet") == 5

    def test_history_disabled_returns_empty(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch, enable_history=False)
        history_file = tmp_path / "history.txt"
        history_file.write_text("- some bullet")
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        assert refine._load_history() == ""
        assert refine._load_history(max_bullets=10) == ""

    def test_missing_file_returns_empty(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        monkeypatch.setattr(refine, "_HISTORY_FILE", tmp_path / "nonexistent.txt")
        assert refine._load_history() == ""

    def test_cap_zero_returns_empty(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        history_file = tmp_path / "history.txt"
        history_file.write_text("- bullet 0\n- bullet 1")
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        result = refine._load_history(max_bullets=0)
        assert result == ""


class TestTierInjection:
    """Verify that refine() calls _load_history with the right argument per tier."""

    def _mock_api(self, monkeypatch, refine, response="cleaned text"):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": response}}]
        }
        import requests
        monkeypatch.setattr(requests, "post", MagicMock(return_value=mock_resp))

    def test_short_tier_no_history(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch, inject_medium=40)
        history_file = tmp_path / "history.txt"
        history_file.write_text("- some project context")
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        self._mock_api(monkeypatch, refine)

        calls = []
        original = refine._load_history
        def spy(*args, **kwargs):
            calls.append(kwargs.get("max_bullets", args[0] if args else None))
            return original(*args, **kwargs)
        monkeypatch.setattr(refine, "_load_history", spy)

        # short text: < 80 words — history must not be injected
        short_text = "Hello world this is a short test."
        monkeypatch.setattr(refine, "_load_context", lambda: "ctx")
        refine.refine(short_text)

        # _load_history should NOT have been called at all for short tier
        assert calls == [], f"Expected no _load_history call for short tier, got: {calls}"

    def test_medium_tier_uses_inject_cap(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch, inject_medium=15)
        history_file = tmp_path / "history.txt"
        history_file.write_text("\n".join(f"- bullet {i}" for i in range(50)))
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        self._mock_api(monkeypatch, refine)

        calls = []
        original = refine._load_history
        def spy(*args, **kwargs):
            calls.append(kwargs.get("max_bullets", args[0] if args else None))
            return original(*args, **kwargs)
        monkeypatch.setattr(refine, "_load_history", spy)

        # medium text: 80–240 words
        medium_text = " ".join(["word"] * 100)
        monkeypatch.setattr(refine, "_load_context", lambda: "ctx")
        refine.refine(medium_text)

        assert len(calls) == 1
        assert calls[0] == 15

    def test_long_tier_no_cap(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch, inject_medium=40)
        history_file = tmp_path / "history.txt"
        history_file.write_text("\n".join(f"- bullet {i}" for i in range(80)))
        monkeypatch.setattr(refine, "_HISTORY_FILE", history_file)
        self._mock_api(monkeypatch, refine)

        calls = []
        original = refine._load_history
        def spy(*args, **kwargs):
            calls.append(kwargs.get("max_bullets", args[0] if args else None))
            return original(*args, **kwargs)
        monkeypatch.setattr(refine, "_load_history", spy)

        # long text: > 240 words
        long_text = " ".join(["word"] * 260)
        monkeypatch.setattr(refine, "_load_context", lambda: "ctx")
        refine.refine(long_text)

        assert len(calls) == 1
        assert calls[0] is None  # no cap for long tier
