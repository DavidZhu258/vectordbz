"""Robust JSON extraction for LLM responses."""

from __future__ import annotations

import json
from typing import Any


def parse_llm_json(content: str) -> Any:
    """Parse the first JSON object/array from a possibly wrapped LLM response."""
    text = _strip_markdown_fence(content.strip())
    decoder = json.JSONDecoder()

    for idx, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(text[idx:])
            return value
        except json.JSONDecodeError:
            continue

    raise ValueError("No JSON object found in LLM response")


def _strip_markdown_fence(text: str) -> str:
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text
