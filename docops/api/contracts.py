"""API contract metadata and validators."""

from __future__ import annotations

from typing import Any

CHAT_RESPONSE_CONTRACT_VERSION = "1.0.0"
CHAT_STREAM_CONTRACT_VERSION = "1.0.0"

CHAT_STREAM_EVENT_TYPES = {"start", "status", "delta", "final", "error", "done"}


def validate_chat_stream_sequence(events: list[dict[str, Any]]) -> list[str]:
    """Validate canonical SSE lifecycle sequence for /api/chat/stream.

    Rules:
    - first event must be ``start``
    - exactly one terminal event: ``done`` (success path) or ``error`` (failure path)
    - success path must emit exactly one ``final`` before ``done``
    - error path must not emit ``final`` or ``done``
    - no events after terminal event
    """
    errors: list[str] = []

    if not events:
        return ["empty event stream"]

    seen_start = 0
    seen_final = 0
    seen_error = 0
    seen_done = 0
    terminal_seen = False

    for idx, event in enumerate(events):
        typ = str(event.get("type") or "").strip()
        if not typ:
            errors.append(f"event[{idx}] missing type")
            continue
        if typ not in CHAT_STREAM_EVENT_TYPES:
            errors.append(f"event[{idx}] has unknown type '{typ}'")
            continue

        if terminal_seen:
            errors.append(f"event[{idx}] appears after terminal event: '{typ}'")
            continue

        if idx == 0 and typ != "start":
            errors.append(f"event[0] must be 'start', got '{typ}'")

        if typ == "start":
            seen_start += 1
            if seen_start > 1:
                errors.append("multiple 'start' events are not allowed")
            continue

        if seen_start == 0:
            errors.append(f"event[{idx}] '{typ}' appears before 'start'")
            continue

        if typ == "final":
            seen_final += 1
            if seen_error > 0:
                errors.append("'final' cannot appear after 'error'")
            if seen_final > 1:
                errors.append("multiple 'final' events are not allowed")
            continue

        if typ == "done":
            seen_done += 1
            terminal_seen = True
            if seen_error > 0:
                errors.append("'done' cannot appear after 'error'")
            if seen_done > 1:
                errors.append("multiple 'done' events are not allowed")
            if seen_final != 1:
                errors.append("'done' requires exactly one prior 'final'")
            continue

        if typ == "error":
            seen_error += 1
            terminal_seen = True
            if seen_error > 1:
                errors.append("multiple 'error' events are not allowed")
            if seen_final > 0:
                errors.append("'error' cannot appear after 'final'")
            continue

        # typ in {"status", "delta"}
        if seen_final > 0:
            errors.append(f"'{typ}' cannot appear after 'final'")
        if seen_error > 0:
            errors.append(f"'{typ}' cannot appear after 'error'")

    if seen_start != 1:
        errors.append(f"expected exactly one 'start', got {seen_start}")

    if seen_error == 0:
        if seen_final != 1:
            errors.append(f"success path requires exactly one 'final', got {seen_final}")
        if seen_done != 1:
            errors.append(f"success path requires exactly one 'done', got {seen_done}")
    else:
        if seen_final != 0:
            errors.append("error path must not include 'final'")
        if seen_done != 0:
            errors.append("error path must not include 'done'")

    return errors
