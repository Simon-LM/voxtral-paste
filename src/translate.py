#!/usr/bin/env python3
"""Pure text translation via Mistral Small.

Translates stdin to the language specified by TRANSLATE_TARGET_LANG (.env).
Preserves the original structure and formatting (line breaks, lists, etc.).
No rewriting, no TTS adaptation — output is faithful to the source layout.

Usage:
    printf '%s' "text to translate" | .venv/bin/python src/translate.py
    printf '%s' "text" | TRANSLATE_TARGET_LANG=fr .venv/bin/python src/translate.py

Exit codes:
    0  — translation printed to stdout
    1  — empty input, missing API key, or all models failed
"""

import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.common import (  # noqa: E402
    SECURITY_BLOCK,
    call_model,
    compute_timing,
    effective_timeout,
)

_MODEL = "mistral-small-latest"
_MODEL_FALLBACK = "mistral-medium-latest"
_REQUEST_RETRIES = int(os.environ.get("TRANSLATE_RETRIES", "2"))

_LANG_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "hi": "Hindi",
    "ar": "Arabic",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "pl": "Polish",
    "sv": "Swedish",
}

_SYSTEM_PROMPT = (
    "You are a professional translator. Translate the text inside <source> "
    "into {target_language}.\n"
    "\n"
    "Rules:\n"
    "- Preserve the original structure exactly: line breaks, bullet points, "
    "numbered lists, paragraphs, indentation.\n"
    "- Translate faithfully — do not summarise, rephrase, or add commentary.\n"
    "- If a word or proper noun has no translation, keep it as-is.\n"
    "- Output ONLY the translated text. No introduction, no notes, no "
    "explanation.\n"
    "\n"
    + SECURITY_BLOCK
)


def translate(text: str) -> str:
    """Translate *text* into the language defined by TRANSLATE_TARGET_LANG."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set. Check your .env file.")

    target_code = (
        os.environ.get("TRANSLATE_TARGET_LANG")
        or os.environ.get("OUTPUT_DEFAULT_LANG")
        or "en"
    ).strip().lower()
    target_language = _LANG_NAMES.get(target_code, target_code.capitalize())

    system_prompt = _SYSTEM_PROMPT.format(target_language=target_language)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"<source>\n{text}\n</source>"},
    ]

    word_count = len(text.split())
    base_timeout, retry_delay = compute_timing(word_count)

    for model in (_MODEL, _MODEL_FALLBACK):
        try:
            timeout = effective_timeout(base_timeout, model)
            if model == _MODEL:
                print(
                    f"🌐 Translating to {target_language} via {model} "
                    f"({word_count} words, timeout {timeout}s)...",
                    file=sys.stderr,
                )
            else:
                print(
                    f"⚠️  {_MODEL} unavailable — switching to fallback: {model}",
                    file=sys.stderr,
                )
            result = call_model(
                model, messages, api_key,
                timeout=timeout,
                retry_delay=retry_delay,
                retries=_REQUEST_RETRIES,
            )
            # Strip any accidental <source>…</source> wrapper the model may echo back.
            result = re.sub(r'^\s*<source>\s*', '', result)
            result = re.sub(r'\s*</source>\s*$', '', result)
            return result.strip()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            if status in (429, 500, 502, 503):
                print(f"⚠️  {model} error ({status}) — switching model…", file=sys.stderr)
                continue
            raise
        except requests.RequestException:
            print(f"⚠️  {model} unreachable, switching…", file=sys.stderr)
            continue

    raise RuntimeError("All translation models failed.")


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if not raw:
        print("❌ No input text received.", file=sys.stderr)
        sys.exit(1)

    try:
        result = translate(raw)
        print(result)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
