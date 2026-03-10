"""Utilities for normalizing LLM response content across providers/models."""

from __future__ import annotations

from typing import Any


def content_to_text(content: Any) -> str:
    """Normalize heterogeneous ``response.content`` payloads to plain text.

    Supports common shapes returned by chat providers:
    - ``str``
    - ``list`` of strings
    - ``list`` of dict blocks (e.g. ``{"type":"text","text":"..."}``)
    - ``dict`` with ``text`` or nested ``parts``/``content`` blocks
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            txt = content_to_text(item)
            if txt:
                parts.append(txt)
        return "\n".join(parts).strip()

    if isinstance(content, dict):
        # Most common block: {"type":"text","text":"..."}
        if isinstance(content.get("text"), str):
            return content["text"]

        # Nested provider payloads
        if "parts" in content:
            return content_to_text(content.get("parts"))
        if "content" in content:
            return content_to_text(content.get("content"))

        # Generic fallback: join string-like values
        values = [v for v in content.values() if isinstance(v, (str, list, dict))]
        return content_to_text(values)

    return str(content)


def response_text(response: Any) -> str:
    """Extract and normalize text from an LLM response object."""
    content = getattr(response, "content", response)
    return content_to_text(content).strip()

