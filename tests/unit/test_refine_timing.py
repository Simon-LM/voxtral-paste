"""Unit tests for _refine_timing() — timeout tier logic and background multiplier.

The background=True flag was added so that history updates (which run after
the text is already in the clipboard) can use doubled timeouts without
penalising the user experience.

The specific bug that prompted this: a 124-word text hit the < 180-word tier
(8s foreground). History extraction with the same text was timing out because
8s was too tight for background API calls. With background=True it now gets
20s (10 × 2).
"""

import sys
import pytest


def _load_refine(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    if "src.refine" in sys.modules:
        del sys.modules["src.refine"]
    import src.refine as rm
    return rm


class TestRefineTiming:
    def test_short_text_foreground_timeout(self, monkeypatch):
        """< 90 words → 6s timeout in normal mode."""
        rm = _load_refine(monkeypatch)
        timeout, _ = rm._refine_timing(50)
        assert timeout == 6

    def test_medium_text_foreground_timeout(self, monkeypatch):
        """< 400 words → 20s timeout in normal mode."""
        rm = _load_refine(monkeypatch)
        timeout, _ = rm._refine_timing(300)
        assert timeout == 20

    def test_background_doubles_timeout(self, monkeypatch):
        """background=True must double the timeout for any tier."""
        rm = _load_refine(monkeypatch)
        fg_timeout, _ = rm._refine_timing(300)
        bg_timeout, _ = rm._refine_timing(300, background=True)
        assert bg_timeout == fg_timeout * 2

    def test_background_does_not_change_retry_delay(self, monkeypatch):
        """retry_delay should be unchanged by the background flag."""
        rm = _load_refine(monkeypatch)
        _, fg_delay = rm._refine_timing(300)
        _, bg_delay = rm._refine_timing(300, background=True)
        assert bg_delay == fg_delay

    def test_bug_fix_124_words_background(self, monkeypatch):
        """124 words + background=True must give 20s (was 8s before fix).

        The real-world failure: history extraction on a 124-word recording
        timed out at 8s. With background=True the tier (< 180) now yields
        10s × 2 = 20s.
        """
        rm = _load_refine(monkeypatch)
        fg_timeout, _ = rm._refine_timing(124)
        bg_timeout, _ = rm._refine_timing(124, background=True)
        assert fg_timeout == 10
        assert bg_timeout == 20
