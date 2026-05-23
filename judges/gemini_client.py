"""Thin wrapper around the Gemini API for the model based judges and the curator.

Every call uses gemini-3.5-flash, no other model. The google-genai SDK is
imported lazily so the package stays importable for the deterministic paths and
the offline self-check without the SDK or an API key present. The key is read
from the environment only.
"""
from __future__ import annotations

import json
from typing import Any

from .config import MODEL, THINKING_BUDGET, gemini_api_key


def get_client():
    """Create a google-genai client using the Gemini key from the environment."""
    from google import genai  # lazy import, keeps the package importable offline

    key = gemini_api_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set in the environment. Set it before live runs."
        )
    return genai.Client(api_key=key)


def extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating code fences and stray prose."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip()
    if s.lower() in ("null", "none", ""):
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start : end + 1])
        raise


def generate_json(
    system: str,
    user: str,
    thinking: str = "medium",
    temperature: float = 0.2,
    client=None,
) -> Any:
    """One gemini-3.5-flash call that returns parsed JSON.

    thinking is one of low, medium, high and maps to a thinking budget. This is
    the default generate callable the judges and curator use; the offline tests
    inject a fake in its place.
    """
    client = client or get_client()
    from google.genai import types

    budget = THINKING_BUDGET.get(thinking, THINKING_BUDGET["medium"])
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=budget),
    )
    try:
        resp = client.models.generate_content(model=MODEL, contents=user, config=config)
    except Exception:
        # Retry with a minimal config for SDK or model variations seen day-of.
        config = types.GenerateContentConfig(
            system_instruction=system, temperature=temperature
        )
        resp = client.models.generate_content(model=MODEL, contents=user, config=config)
    return extract_json(resp.text)
