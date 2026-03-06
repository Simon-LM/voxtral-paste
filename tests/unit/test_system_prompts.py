"""Unit tests for system prompt templates.

Verifies that all 3 prompts are well-formed and contain the required directives.
"""

import sys

import pytest


def _get_refine(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    if "src.refine" in sys.modules:
        del sys.modules["src.refine"]
    import src.refine as refine
    return refine


PROMPTS = ["_SYSTEM_PROMPT_SHORT", "_SYSTEM_PROMPT_MEDIUM", "_SYSTEM_PROMPT_LONG"]


class TestPromptFormatting:
    @pytest.mark.parametrize("prompt_name", PROMPTS)
    def test_format_with_context_does_not_raise(self, monkeypatch, prompt_name):
        refine = _get_refine(monkeypatch)
        prompt = getattr(refine, prompt_name)
        result = prompt.format(context="Some context.")
        assert isinstance(result, str)

    @pytest.mark.parametrize("prompt_name", PROMPTS)
    def test_context_injected_in_output(self, monkeypatch, prompt_name):
        refine = _get_refine(monkeypatch)
        prompt = getattr(refine, prompt_name)
        result = prompt.format(context="MySpecificContext")
        assert "MySpecificContext" in result

    @pytest.mark.parametrize("prompt_name", PROMPTS)
    def test_context_xml_tags_present(self, monkeypatch, prompt_name):
        refine = _get_refine(monkeypatch)
        prompt = getattr(refine, prompt_name)
        result = prompt.format(context="x")
        assert "<context>" in result

    @pytest.mark.parametrize("prompt_name", PROMPTS)
    def test_language_rule_present(self, monkeypatch, prompt_name):
        """All prompts must include the CRITICAL language rule."""
        refine = _get_refine(monkeypatch)
        prompt = getattr(refine, prompt_name)
        result = prompt.format(context="x")
        assert "CRITICAL" in result
        assert "Never translate" in result

    @pytest.mark.parametrize("prompt_name", PROMPTS)
    def test_no_untranslated_placeholder(self, monkeypatch, prompt_name):
        """After formatting, no {placeholder} should remain."""
        refine = _get_refine(monkeypatch)
        prompt = getattr(refine, prompt_name)
        result = prompt.format(context="x")
        assert "{context}" not in result


class TestPromptDifferentiation:
    def test_short_prompt_shorter_than_medium(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        short = refine._SYSTEM_PROMPT_SHORT.format(context="x")
        medium = refine._SYSTEM_PROMPT_MEDIUM.format(context="x")
        assert len(short) < len(medium)

    def test_long_prompt_contains_prose_instruction(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        long_prompt = refine._SYSTEM_PROMPT_LONG.format(context="x")
        assert "prose" in long_prompt.lower()

    def test_medium_prompt_does_not_contain_prose_instruction(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        medium_prompt = refine._SYSTEM_PROMPT_MEDIUM.format(context="x")
        assert "well-structured written prose" not in medium_prompt
