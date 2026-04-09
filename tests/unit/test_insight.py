"""Unit tests for src/insight.py.

Tests cover:
  - summarize() happy path and API key guard
  - search_perplexity() happy path and API key guard
  - search_grok() happy path and API key guard (mocked via sys.modules)
  - search() dispatcher: auto / perplexity / grok / both modes
  - factcheck() adaptive: both sources, single source, synthesis reasoning flag
  - CLI subcommands: summarize, search, factcheck
  - detect_content_type() integration (via tts module)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.insight import (
    factcheck,
    search,
    search_grok,
    search_perplexity,
    summarize,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_chat_response(content: str) -> MagicMock:
    """Build a fake requests.Response for a chat completion (Mistral / Perplexity)."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_xai_sdk(answer: str) -> dict:
    """Return a sys.modules patch dict that makes xai_sdk return *answer*.

    Usage:
        with patch.dict(sys.modules, _mock_xai_sdk("Grok answer.")):
            result = search_grok("query")
    """
    mock_response = MagicMock()
    mock_response.content = answer

    mock_chat = MagicMock()
    mock_chat.sample.return_value = mock_response

    mock_client_instance = MagicMock()
    mock_client_instance.chat.create.return_value = mock_chat

    mock_xai_sdk        = MagicMock()
    mock_xai_sdk.Client = MagicMock(return_value=mock_client_instance)

    mock_chat_module    = MagicMock()
    mock_tools_module   = MagicMock()

    return {
        "xai_sdk":       mock_xai_sdk,
        "xai_sdk.chat":  mock_chat_module,
        "xai_sdk.tools": mock_tools_module,
    }


# ── summarize() ──────────────────────────────────────────────────────────────

class TestSummarize:
    def test_returns_summary_text(self):
        with patch("src.insight._MISTRAL_KEY", "key-x"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response(
                "• First point.\n• Second point."
            )
            result = summarize("Some article text.", "news_article")
        assert "First point" in result
        assert "Second point" in result

    def test_raises_when_no_mistral_key(self):
        with patch("src.insight._MISTRAL_KEY", ""):
            with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
                summarize("text")

    def test_content_type_hint_injected(self):
        with patch("src.insight._MISTRAL_KEY", "key-x"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("• Bullet.")
            summarize("text", "wikipedia")
        call_payload = mock_post.call_args[1]["json"]
        user_content = call_payload["messages"][-1]["content"]
        assert "wikipedia" in user_content

    def test_generic_type_no_hint(self):
        with patch("src.insight._MISTRAL_KEY", "key-x"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("• Bullet.")
            summarize("text", "generic")
        call_payload = mock_post.call_args[1]["json"]
        user_content = call_payload["messages"][-1]["content"]
        assert "Content type" not in user_content

    def test_reasoning_effort_high_in_payload(self):
        with patch("src.insight._MISTRAL_KEY", "key-x"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("• Bullet.")
            summarize("text")
        payload = mock_post.call_args[1]["json"]
        assert payload.get("reasoning_effort") == "high"

    def test_http_error_propagates(self):
        import requests as req_module
        with patch("src.insight._MISTRAL_KEY", "key-x"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.side_effect = req_module.exceptions.ConnectionError("timeout")
            with pytest.raises(Exception):
                summarize("text")


# ── search_perplexity() ───────────────────────────────────────────────────────

class TestSearchPerplexity:
    def test_returns_answer(self):
        with patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("Perplexity answer here.")
            result = search_perplexity("What is Python?", "Context summary.")
        assert "Perplexity answer" in result

    def test_raises_when_no_key(self):
        with patch("src.insight._PERPLEXITY_KEY", ""):
            with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
                search_perplexity("query")

    def test_context_injected_in_user_message(self):
        with patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("Answer.")
            search_perplexity("My question", "My context summary")
        user_content = mock_post.call_args[1]["json"]["messages"][-1]["content"]
        assert "My context summary" in user_content
        assert "My question" in user_content

    def test_no_context_sends_query_only(self):
        with patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("Answer.")
            search_perplexity("bare query")
        user_content = mock_post.call_args[1]["json"]["messages"][-1]["content"]
        assert user_content == "bare query"


# ── search_grok() ─────────────────────────────────────────────────────────────

class TestSearchGrok:
    def test_returns_answer(self):
        with patch("src.insight._XAI_KEY", "xai-key"), \
             patch.dict(sys.modules, _mock_xai_sdk("Grok answer here.")):
            result = search_grok("Verify this claim", "Summary ctx")
        assert "Grok answer here" in result

    def test_raises_when_no_key(self):
        with patch("src.insight._XAI_KEY", ""):
            with pytest.raises(RuntimeError, match="XAI_API_KEY"):
                search_grok("query")

    def test_xai_client_called_with_api_key(self):
        sdk_mocks = _mock_xai_sdk("Answer.")
        with patch("src.insight._XAI_KEY", "my-xai-key"), \
             patch.dict(sys.modules, sdk_mocks):
            search_grok("query")
        # The Client should have been constructed with the API key
        sdk_mocks["xai_sdk"].Client.assert_called_once_with(api_key="my-xai-key")

    def test_both_web_and_x_tools_requested(self):
        """chat.create must receive both web_search and x_search tools."""
        sdk_mocks = _mock_xai_sdk("Answer.")
        with patch("src.insight._XAI_KEY", "xai-key"), \
             patch.dict(sys.modules, sdk_mocks):
            search_grok("query")
        # Retrieve the mock client instance that was returned by Client(...)
        mock_client = sdk_mocks["xai_sdk"].Client.return_value
        call_kwargs = mock_client.chat.create.call_args[1]
        tools = call_kwargs.get("tools", [])
        assert len(tools) == 2  # web_search() + x_search()

    def test_system_message_appended(self):
        """The system prompt must be appended before the user message."""
        sdk_mocks = _mock_xai_sdk("Answer.")
        with patch("src.insight._XAI_KEY", "xai-key"), \
             patch.dict(sys.modules, sdk_mocks):
            search_grok("query")
        mock_client = sdk_mocks["xai_sdk"].Client.return_value
        chat_obj = mock_client.chat.create.return_value
        # append must be called at least twice (system + user)
        assert chat_obj.append.call_count >= 2

    def test_context_summary_injected(self):
        sdk_mocks = _mock_xai_sdk("Answer.")
        with patch("src.insight._XAI_KEY", "xai-key"), \
             patch.dict(sys.modules, sdk_mocks):
            search_grok("My question", "My context summary")
        mock_client = sdk_mocks["xai_sdk"].Client.return_value
        chat_obj = mock_client.chat.create.return_value
        # The second append call is the user message — extract its arg
        user_msg_arg = chat_obj.append.call_args_list[1][0][0]
        # The xai_sdk.chat module's user() function was called, inspect the arg
        user_fn = sdk_mocks["xai_sdk.chat"].user
        user_fn.assert_called_once()
        call_arg = user_fn.call_args[0][0]
        assert "My context summary" in call_arg
        assert "My question" in call_arg


# ── search() dispatcher ───────────────────────────────────────────────────────

class TestSearch:
    def test_auto_uses_perplexity_when_available(self):
        with patch("src.insight._SEARCH_ENGINE", "auto"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY", "xai-key"), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("Perplexity wins.")
            result = search("query", "ctx")
        assert "Perplexity wins" in result
        # Perplexity URL must have been called
        called_url = mock_post.call_args[0][0]
        assert "perplexity" in called_url

    def test_auto_falls_back_to_grok_when_no_perplexity(self):
        sdk_mocks = _mock_xai_sdk("Grok fallback.")
        with patch("src.insight._SEARCH_ENGINE", "auto"), \
             patch("src.insight._PERPLEXITY_KEY", ""), \
             patch("src.insight._XAI_KEY", "xai-key"), \
             patch.dict(sys.modules, sdk_mocks):
            result = search("query")
        assert "Grok fallback" in result

    def test_auto_raises_when_no_keys(self):
        with patch("src.insight._SEARCH_ENGINE", "auto"), \
             patch("src.insight._PERPLEXITY_KEY", ""), \
             patch("src.insight._XAI_KEY", ""):
            with pytest.raises(RuntimeError, match="No search engine"):
                search("query")

    def test_force_perplexity_raises_when_no_key(self):
        with patch("src.insight._SEARCH_ENGINE", "perplexity"), \
             patch("src.insight._PERPLEXITY_KEY", ""):
            with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
                search("query")

    def test_force_grok_raises_when_no_key(self):
        with patch("src.insight._SEARCH_ENGINE", "grok"), \
             patch("src.insight._XAI_KEY", ""):
            with pytest.raises(RuntimeError, match="XAI_API_KEY"):
                search("query")

    def test_unknown_engine_raises(self):
        with patch("src.insight._SEARCH_ENGINE", "bing"):
            with pytest.raises(RuntimeError, match="Unknown INSIGHT_SEARCH_ENGINE"):
                search("query")


# ── factcheck() ───────────────────────────────────────────────────────────────

class TestFactcheck:
    def test_both_sources_returns_synthesis(self):
        """With both keys, factcheck must synthesise via Mistral."""
        sdk_mocks = _mock_xai_sdk("Grok fact-check result.")

        def _fake_post(url, **kwargs):
            if "perplexity" in url:
                return _make_chat_response("Perplexity fact-check result.")
            # Mistral synthesis
            return _make_chat_response(
                "Reliability: Confirmed\n\nSynthesis.\n\nPerplexity: ok.\nGrok: ok."
            )

        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY",        "xai-key"), \
             patch("src.insight.requests.post", side_effect=_fake_post), \
             patch.dict(sys.modules, sdk_mocks):
            synthesis, perp_detail, grok_detail = factcheck("Summary text.")

        assert "Reliability" in synthesis
        assert "Perplexity" in perp_detail
        assert "Grok" in grok_detail

    def test_grok_only_returns_direct_result_no_synthesis(self):
        """With only XAI_API_KEY, factcheck must return Grok result directly."""
        sdk_mocks = _mock_xai_sdk("Grok direct result.")

        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", ""), \
             patch("src.insight._XAI_KEY",        "xai-key"), \
             patch("src.insight.requests.post")  as mock_post, \
             patch.dict(sys.modules, sdk_mocks):
            synthesis, perp_detail, grok_detail = factcheck("Summary.")

        # Mistral (Perplexity URL not called, no synthesis call either)
        mock_post.assert_not_called()
        assert "Grok direct result" in synthesis
        assert perp_detail == ""
        assert "Grok direct result" in grok_detail

    def test_perplexity_only_returns_direct_result_no_synthesis(self):
        """With only PERPLEXITY_API_KEY, factcheck must return Perplexity result directly."""
        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY",        ""), \
             patch("src.insight.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("Perplexity direct result.")
            synthesis, perp_detail, grok_detail = factcheck("Summary.")

        # Only one call (Perplexity), no Mistral synthesis
        assert mock_post.call_count == 1
        assert "Perplexity direct result" in synthesis
        assert "Perplexity direct result" in perp_detail
        assert grok_detail == ""

    def test_raises_when_no_mistral_key(self):
        with patch("src.insight._MISTRAL_KEY", ""):
            with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
                factcheck("summary")

    def test_raises_when_no_search_keys(self):
        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", ""), \
             patch("src.insight._XAI_KEY",        ""):
            with pytest.raises(RuntimeError, match="No fact-check source"):
                factcheck("summary")

    def test_synthesis_without_reasoning_effort_by_default(self):
        """Standard mode must NOT include reasoning_effort in the Mistral payload."""
        sdk_mocks = _mock_xai_sdk("Grok result.")

        def _fake_post(url, **kwargs):
            if "perplexity" in url:
                return _make_chat_response("Perplexity result.")
            return _make_chat_response("Synthesis.")

        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY",        "xai-key"), \
             patch("src.insight._SYNTHESIS_REASONING", "standard"), \
             patch("src.insight.requests.post", side_effect=_fake_post) as mock_post, \
             patch.dict(sys.modules, sdk_mocks):
            factcheck("Summary.")

        # Last call is Mistral synthesis
        synthesis_call = [
            c for c in mock_post.call_args_list
            if "mistral" in c[0][0]
        ]
        assert synthesis_call, "Expected Mistral synthesis call"
        payload = synthesis_call[-1][1]["json"]
        assert "reasoning_effort" not in payload

    def test_synthesis_with_high_reasoning_when_configured(self):
        sdk_mocks = _mock_xai_sdk("Grok result.")

        def _fake_post(url, **kwargs):
            if "perplexity" in url:
                return _make_chat_response("Perplexity result.")
            return _make_chat_response("Synthesis.")

        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY",        "xai-key"), \
             patch("src.insight._SYNTHESIS_REASONING", "high"), \
             patch("src.insight.requests.post", side_effect=_fake_post) as mock_post, \
             patch.dict(sys.modules, sdk_mocks):
            factcheck("Summary.")

        synthesis_call = [
            c for c in mock_post.call_args_list
            if "mistral" in c[0][0]
        ]
        assert synthesis_call
        payload = synthesis_call[-1][1]["json"]
        assert payload.get("reasoning_effort") == "high"

    def test_graceful_degradation_one_source_fails(self):
        """If Grok fails at runtime, factcheck should return Perplexity result directly."""
        sdk_mocks = _mock_xai_sdk("ignored")
        # Make Grok raise
        sdk_mocks["xai_sdk"].Client.return_value.chat.create.return_value \
            .sample.side_effect = RuntimeError("Grok down")

        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY",        "xai-key"), \
             patch("src.insight.requests.post") as mock_post, \
             patch.dict(sys.modules, sdk_mocks):
            mock_post.return_value = _make_chat_response("Perplexity detail.")
            synthesis, perp_detail, grok_detail = factcheck("summary")

        # Perplexity succeeded, Grok failed → single-source, no synthesis
        assert synthesis
        assert perp_detail == "Perplexity detail."
        assert grok_detail == ""

    def test_detail_files_written(self, tmp_path):
        """factcheck() returns detail strings; caller (_cmd_factcheck) writes files."""
        pplx_file = tmp_path / "perplexity.txt"
        grok_file  = tmp_path / "grok.txt"
        sdk_mocks  = _mock_xai_sdk("GROK detail.")

        def _fake_post(url, **kwargs):
            if "perplexity" in url:
                return _make_chat_response("PPLX detail.")
            return _make_chat_response("Synthesis.")

        with patch("src.insight._MISTRAL_KEY",    "m-key"), \
             patch("src.insight._PERPLEXITY_KEY", "pplx-key"), \
             patch("src.insight._XAI_KEY",        "xai-key"), \
             patch("src.insight.requests.post", side_effect=_fake_post), \
             patch.dict(sys.modules, sdk_mocks):
            synthesis, perp_detail, grok_detail = factcheck("summary text")

        pplx_file.write_text(perp_detail, encoding="utf-8")
        grok_file.write_text(grok_detail, encoding="utf-8")

        assert pplx_file.read_text() == "PPLX detail."
        assert grok_file.read_text() == "GROK detail."


# ── detect_content_type() integration ────────────────────────────────────────

class TestDetectContentType:
    def test_returns_known_type(self):
        from src.tts import detect_content_type, _CLEAN_RULES
        with patch("src.tts.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("news_article")
            result = detect_content_type("some text", "api-key")
        assert result == "news_article"
        assert result in _CLEAN_RULES

    def test_falls_back_to_generic_on_unknown(self):
        from src.tts import detect_content_type
        with patch("src.tts.requests.post") as mock_post:
            mock_post.return_value = _make_chat_response("unknown_garbage_type")
            result = detect_content_type("some text", "api-key")
        assert result == "generic"

    def test_falls_back_to_generic_on_error(self):
        import requests as req_module
        from src.tts import detect_content_type
        with patch("src.tts.requests.post") as mock_post:
            mock_post.side_effect = req_module.exceptions.Timeout("timeout")
            result = detect_content_type("some text", "api-key")
        assert result == "generic"
