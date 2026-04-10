#!/usr/bin/env python3
"""Step 1 (F8/F9): Image file → extracted text via Mistral OCR API.

Primary:  mistral-ocr-latest  (/v1/ocr)
Fallback: pixtral-12b         (/v1/chat/completions, vision prompt)
"""

import base64
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_OCR_URL = "https://api.mistral.ai/v1/ocr"
_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
_OCR_MODEL = "mistral-ocr-latest"
_FALLBACK_MODEL = "pixtral-large-latest"
_TIMEOUT = 30
_RETRIES = 2
_RETRY_DELAY = 2.0
_TRANSIENT_HTTP_CODES = (429, 500, 502, 503)

_FALLBACK_PROMPT = (
    "Extract all text from this image exactly as it appears, "
    "preserving line breaks and structure. Output only the extracted text, "
    "no commentary."
)


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _mime_type(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix.lstrip("."), "image/png"
    )


def _request_with_retry(url: str, headers: dict, payload: dict) -> dict:
    """POST with retry on transient errors. Returns parsed JSON body."""
    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(1 + _RETRIES):
        if attempt > 0:
            print(
                f"  ⏳  OCR — retry {attempt}/{_RETRIES} (waiting {_RETRY_DELAY:.0f}s)…",
                file=sys.stderr,
            )
            time.sleep(_RETRY_DELAY)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            if code in _TRANSIENT_HTTP_CODES:
                label = "rate limit (429)" if code == 429 else f"server error ({code})"
                print(f"  ⚠️  OCR {label} — will retry…", file=sys.stderr)
                last_exc = exc
                continue
            raise
        except requests.Timeout as exc:
            print(f"  ⏱  OCR timed out ({_TIMEOUT}s) — will retry…", file=sys.stderr)
            last_exc = exc
            continue
    raise last_exc


def _extract_primary(image_b64: str, mime: str, api_key: str) -> str:
    """Call mistral-ocr-latest."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _OCR_MODEL,
        "document": {
            "type": "image_url",
            "image_url": f"data:{mime};base64,{image_b64}",
        },
    }
    body = _request_with_retry(_OCR_URL, headers, payload)
    pages = body.get("pages", [])
    if not pages:
        raise RuntimeError(f"Empty OCR response: {body}")
    return "\n\n".join(p.get("markdown", "") for p in pages).strip()


def _extract_fallback(image_b64: str, mime: str, api_key: str) -> str:
    """Call pixtral-12b via chat completions as fallback."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _FALLBACK_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:{mime};base64,{image_b64}",
                    },
                    {"type": "text", "text": _FALLBACK_PROMPT},
                ],
            }
        ],
    }
    body = _request_with_retry(_CHAT_URL, headers, payload)
    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError(f"Empty fallback response: {body}")
    return choices[0].get("message", {}).get("content", "").strip()


def ocr(image_path: str) -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set. Check your .env file.")

    size = Path(image_path).stat().st_size
    print(f"  🖼  Image read: {size} bytes.", file=sys.stderr)
    print(f"  🔍 Running OCR via {_OCR_MODEL}...", file=sys.stderr)

    image_b64 = _encode_image(image_path)
    mime = _mime_type(image_path)

    try:
        return _extract_primary(image_b64, mime, api_key)
    except Exception as exc:
        print(f"  ⚠️  {_OCR_MODEL} failed ({exc}) — falling back to {_FALLBACK_MODEL}…",
              file=sys.stderr)

    print(f"  🔍 Running OCR via {_FALLBACK_MODEL} (fallback)...", file=sys.stderr)
    return _extract_fallback(image_b64, mime, api_key)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ocr.py <image_file>", file=sys.stderr)
        sys.exit(1)

    image_file = sys.argv[1]

    if not Path(image_file).exists():
        print(f"❌ File not found: {image_file}", file=sys.stderr)
        sys.exit(1)

    result = ocr(image_file)
    print(result)  # stdout only — captured by the shell script
