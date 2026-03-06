"""Unit tests for _load_context() — filesystem behaviour."""

import sys

import pytest


def _get_refine(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    if "src.refine" in sys.modules:
        del sys.modules["src.refine"]
    import src.refine as refine
    return refine


class TestLoadContext:
    def test_returns_file_content_when_present(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        context_file = tmp_path / "context.txt"
        context_file.write_text("Python developer, uses pytest.", encoding="utf-8")

        monkeypatch.setattr(refine, "_CONTEXT_FILE", context_file)
        assert refine._load_context() == "Python developer, uses pytest."

    def test_strips_surrounding_whitespace(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        context_file = tmp_path / "context.txt"
        context_file.write_text("  some context  \n\n", encoding="utf-8")

        monkeypatch.setattr(refine, "_CONTEXT_FILE", context_file)
        assert refine._load_context() == "some context"

    def test_returns_default_when_file_missing(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        missing = tmp_path / "context.txt"  # not created

        monkeypatch.setattr(refine, "_CONTEXT_FILE", missing)
        assert refine._load_context() == "No context defined."

    def test_handles_empty_file(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        context_file = tmp_path / "context.txt"
        context_file.write_text("", encoding="utf-8")

        monkeypatch.setattr(refine, "_CONTEXT_FILE", context_file)
        assert refine._load_context() == ""

    def test_handles_multiline_content(self, monkeypatch, tmp_path):
        refine = _get_refine(monkeypatch)
        context_file = tmp_path / "context.txt"
        content = "Backend developer.\nStack: Python, FastAPI, PostgreSQL."
        context_file.write_text(content, encoding="utf-8")

        monkeypatch.setattr(refine, "_CONTEXT_FILE", context_file)
        assert refine._load_context() == content
