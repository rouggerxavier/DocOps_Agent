"""Short-lived active context memory for chat sessions."""

from __future__ import annotations

from typing import Any

_DEFAULT_CONTEXT: dict[str, Any] = {
    "active_doc_ids": [],
    "active_doc_names": [],
    "active_deck_id": None,
    "active_deck_title": None,
    "active_task_id": None,
    "active_task_title": None,
    "active_note_id": None,
    "active_note_title": None,
    "active_intent": None,
    "last_action": None,
    "last_user_command": None,
    "last_card_count": None,
    "last_difficulty_mix": None,
}

_session_contexts: dict[tuple[int, str], dict[str, Any]] = {}


def _session_key(user_id: int, session_id: str | None) -> tuple[int, str]:
    return (int(user_id), str(session_id or "__default__"))


def normalize_active_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(_DEFAULT_CONTEXT)
    if not raw:
        return context

    for key in (
        "active_doc_ids",
        "active_doc_names",
    ):
        values = raw.get(key) or []
        if isinstance(values, list):
            cleaned = [str(item).strip() for item in values if str(item).strip()]
            context[key] = list(dict.fromkeys(cleaned))[:10]

    for key in (
        "active_deck_title",
        "active_task_title",
        "active_note_title",
        "active_intent",
        "last_action",
        "last_user_command",
    ):
        value = raw.get(key)
        context[key] = str(value).strip()[:500] if value is not None and str(value).strip() else None

    for key in ("active_deck_id", "active_task_id", "active_note_id", "last_card_count"):
        value = raw.get(key)
        try:
            context[key] = int(value) if value is not None else None
        except (TypeError, ValueError):
            context[key] = None

    mix = raw.get("last_difficulty_mix")
    if isinstance(mix, dict):
        normalized_mix: dict[str, int] = {}
        for name in ("facil", "media", "dificil"):
            value = mix.get(name)
            try:
                normalized_mix[name] = max(0, int(value))
            except (TypeError, ValueError):
                normalized_mix[name] = 0
        context["last_difficulty_mix"] = normalized_mix

    return context


def merge_active_context(base: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = normalize_active_context(base)
    patch_context = normalize_active_context(patch)

    for key, value in patch_context.items():
        if key in {"active_doc_ids", "active_doc_names"}:
            if value:
                merged[key] = value
            continue
        if value is not None:
            merged[key] = value

    # If one side provided docs and the other did not, keep the existing docs.
    if not patch_context.get("active_doc_ids"):
        merged["active_doc_ids"] = merged.get("active_doc_ids") or normalize_active_context(base).get("active_doc_ids", [])
    if not patch_context.get("active_doc_names"):
        merged["active_doc_names"] = merged.get("active_doc_names") or normalize_active_context(base).get("active_doc_names", [])

    return normalize_active_context(merged)


def get_active_context(user_id: int, session_id: str | None) -> dict[str, Any]:
    return normalize_active_context(_session_contexts.get(_session_key(user_id, session_id)))


def remember_active_context(user_id: int, session_id: str | None, context: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_active_context(context)
    _session_contexts[_session_key(user_id, session_id)] = normalized
    return normalized


def clear_active_context(user_id: int, session_id: str | None) -> None:
    _session_contexts.pop(_session_key(user_id, session_id), None)
