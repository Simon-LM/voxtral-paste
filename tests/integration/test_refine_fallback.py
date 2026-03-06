"""Integration tests for refine() — fallback and error handling.

All HTTP calls are mocked — no real network requests are made.
"""

import sys
from unittest.mock import MagicMock, call

import pytest
import requests


def _get_refine(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    if "src.refine" in sys.modules:
        del sys.modules["src.refine"]
    import src.refine as refine
    return refine


def _ok_response(text: str) -> MagicMock:
    """Build a mock HTTP response that returns a successful refinement."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": text}}]
    }
    return resp


def _error_response(status_code: int, body: str = "") -> MagicMock:
    """Build a mock HTTP response that raises HTTPError with the given status."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    http_error = requests.HTTPError(response=resp)
    resp.raise_for_status = MagicMock(side_effect=http_error)
    return resp


class TestRefineHappyPath:
    def test_returns_refined_text_on_success(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        monkeypatch.setattr(requests, "post", MagicMock(return_value=_ok_response("Clean text.")))
        result = refine.refine("uh so this is a test")
        assert result == "Clean text."

    def test_no_api_key_raises_runtime_error(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        monkeypatch.setenv("MISTRAL_API_KEY", "")  # empty string is falsy
        with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
            refine.refine("some text")


class TestRefineFallbackOn429:
    def test_primary_429_triggers_fallback(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        mock_post = MagicMock(side_effect=[
            _error_response(429, '{"message":"Too Many Requests"}'),
            _ok_response("Fallback result."),
        ])
        monkeypatch.setattr(requests, "post", mock_post)
        result = refine.refine("uh so this is a test")
        assert result == "Fallback result."
        assert mock_post.call_count == 2

    def test_primary_500_triggers_fallback(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        mock_post = MagicMock(side_effect=[
            _error_response(500, "Internal Server Error"),
            _ok_response("Fallback result."),
        ])
        monkeypatch.setattr(requests, "post", mock_post)
        result = refine.refine("uh so this is a test")
        assert result == "Fallback result."

    def test_primary_503_triggers_fallback(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        mock_post = MagicMock(side_effect=[
            _error_response(503, "Service Unavailable"),
            _ok_response("Fallback result."),
        ])
        monkeypatch.setattr(requests, "post", mock_post)
        result = refine.refine("uh so this is a test")
        assert result == "Fallback result."


class TestRefineAllModelsFail:
    def test_returns_raw_text_when_all_models_fail_429(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        raw = "uh so this is the raw text"
        mock_post = MagicMock(side_effect=[
            _error_response(429),
            _error_response(429),
        ])
        monkeypatch.setattr(requests, "post", mock_post)
        result = refine.refine(raw)
        assert result == raw

    def test_returns_raw_text_when_all_models_timeout(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        raw = "uh so this is the raw text"
        monkeypatch.setattr(
            requests, "post",
            MagicMock(side_effect=requests.Timeout("timed out")),
        )
        result = refine.refine(raw)
        assert result == raw

    def test_returns_raw_text_when_all_models_connection_error(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        raw = "network failure test"
        monkeypatch.setattr(
            requests, "post",
            MagicMock(side_effect=requests.ConnectionError("no route")),
        )
        result = refine.refine(raw)
        assert result == raw


class TestRefineNonRetryableError:
    def test_401_propagates_immediately(self, monkeypatch):
        """A 401 Unauthorized should not trigger fallback — it re-raises."""
        refine = _get_refine(monkeypatch)
        mock_post = MagicMock(return_value=_error_response(401, "Unauthorized"))
        monkeypatch.setattr(requests, "post", mock_post)
        with pytest.raises(requests.HTTPError):
            refine.refine("some text")
        # Only 1 call — no fallback attempted for auth failures
        assert mock_post.call_count == 1

    def test_403_propagates_immediately(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        mock_post = MagicMock(return_value=_error_response(403, "Forbidden"))
        monkeypatch.setattr(requests, "post", mock_post)
        with pytest.raises(requests.HTTPError):
            refine.refine("some text")
        assert mock_post.call_count == 1


class TestRefineUserMessageFormat:
    def test_user_message_wraps_text_in_xml_tags(self, monkeypatch):
        refine = _get_refine(monkeypatch)
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["messages"] = json["messages"]
            return _ok_response("ok")

        monkeypatch.setattr(requests, "post", fake_post)
        refine.refine("hello world")
        user_msg = captured["messages"][1]["content"]
        assert user_msg.startswith("<transcription>")
        assert user_msg.endswith("</transcription>")
        assert "hello world" in user_msg
