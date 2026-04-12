"""Contract tests for /api/chat and /api/chat/stream."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set env vars before app import.
os.environ.setdefault("JWT_SECRET_KEY", "contract-tests-secret")
os.environ.setdefault("GEMINI_API_KEY", "contract-tests-fake-key")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from docops.api.app import app
from docops.api.contracts import (
    CHAT_RESPONSE_CONTRACT_VERSION,
    CHAT_STREAM_CONTRACT_VERSION,
    validate_chat_stream_sequence,
)
from docops.auth.dependencies import get_current_user
from docops.db.database import Base, get_db
from docops.db.models import User


SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"
_MISSING = object()

_TEST_DB_URL = "sqlite:///:memory:"
_test_engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def _override_get_db():
    Base.metadata.create_all(bind=_test_engine)
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


def _load_snapshot(name: str) -> dict[str, Any]:
    return json.loads((SNAPSHOTS_DIR / name).read_text(encoding="utf-8"))


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    raise ValueError(f"Unknown expected type '{expected}'")


def _assert_object_types(
    obj: dict[str, Any],
    spec: dict[str, Any],
    *,
    label: str,
) -> None:
    expected_keys = set(spec.keys())
    actual_keys = set(obj.keys())
    assert actual_keys == expected_keys, (
        f"{label}: keys changed.\nexpected={sorted(expected_keys)}\nactual={sorted(actual_keys)}"
    )

    for key, expected_type in spec.items():
        value = obj.get(key)
        allowed = expected_type if isinstance(expected_type, list) else [expected_type]
        assert any(_type_matches(value, t) for t in allowed), (
            f"{label}.{key} type mismatch: expected {allowed}, got {type(value).__name__}"
        )


def _parse_sse_events(response_text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[6:])
        for line in response_text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def auth_client():
    fake_user = User(
        id=1,
        name="Contract Tester",
        email="contract@example.com",
        password_hash="x",
        is_active=True,
    )

    previous_auth = app.dependency_overrides.get(get_current_user, _MISSING)
    previous_db = app.dependency_overrides.get(get_db, _MISSING)

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        yield client

    if previous_auth is _MISSING:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous_auth

    if previous_db is _MISSING:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_db


def _patch_chat_dependencies(monkeypatch: pytest.MonkeyPatch, *, fail_stream: bool = False) -> None:
    from langchain_core.documents import Document

    if fail_stream:
        def _boom(*_args, **_kwargs):
            raise EnvironmentError("stream contract forced failure")
        monkeypatch.setattr("docops.api.routes.chat._run_chat", _boom)
    else:
        fake_state = {
            "answer": "Resposta de contrato [Fonte 1]",
            "intent": "qa",
            "retrieved_chunks": [
                Document(
                    page_content="evidencia do contrato",
                    metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "c-1"},
                )
            ],
            "grounding_info": {"support_rate": 0.91, "unsupported_claims": []},
        }
        monkeypatch.setattr(
            "docops.api.routes.chat._run_chat",
            lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
        )

    # Keep contract tests deterministic and fully offline.
    monkeypatch.setattr("docops.api.routes.chat.maybe_answer_calendar_query", lambda *a, **k: None)
    monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", lambda *a, **k: None)
    monkeypatch.setattr(
        "docops.api.routes.chat._resolve_doc_context",
        lambda *_a, **_k: {"active_doc_ids": [], "active_doc_names": []},
    )


def test_chat_response_contract_snapshot(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _patch_chat_dependencies(monkeypatch)
    snapshot = _load_snapshot("chat_response.contract.json")

    assert snapshot["version"] == CHAT_RESPONSE_CONTRACT_VERSION

    resp = auth_client.post("/api/chat", json={"message": "oi", "session_id": "contract-s1"})
    assert resp.status_code == 200

    payload = resp.json()
    _assert_object_types(payload, snapshot["top_level_field_types"], label="chat_response")

    assert payload["sources"], "chat_response.sources must include at least one item for contract check"
    _assert_object_types(
        payload["sources"][0],
        snapshot["source_item_field_types"],
        label="chat_response.sources[0]",
    )

    assert payload["quality_signal"] is not None
    _assert_object_types(
        payload["quality_signal"],
        snapshot["quality_signal_field_types"],
        label="chat_response.quality_signal",
    )

    assert payload["active_context"] is not None
    _assert_object_types(
        payload["active_context"],
        snapshot["active_context_field_types"],
        label="chat_response.active_context",
    )


def test_chat_stream_contract_snapshot_success(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _patch_chat_dependencies(monkeypatch)
    chat_snapshot = _load_snapshot("chat_response.contract.json")
    stream_snapshot = _load_snapshot("chat_stream.contract.json")

    assert stream_snapshot["version"] == CHAT_STREAM_CONTRACT_VERSION

    resp = auth_client.post("/api/chat/stream", json={"message": "oi", "session_id": "contract-s2"})
    assert resp.status_code == 200

    events = _parse_sse_events(resp.text)
    sequence_errors = validate_chat_stream_sequence(events)
    assert not sequence_errors, f"invalid SSE sequence: {sequence_errors}"

    event_specs = stream_snapshot["event_field_types"]
    for idx, event in enumerate(events):
        event_type = event.get("type")
        assert event_type in event_specs, f"unknown SSE event type at index {idx}: {event_type}"
        _assert_object_types(event, event_specs[event_type], label=f"chat_stream.event[{idx}]")

    final_event = next(event for event in events if event.get("type") == "final")
    _assert_object_types(
        final_event["response"],
        chat_snapshot["top_level_field_types"],
        label="chat_stream.final.response",
    )


def test_chat_stream_contract_snapshot_error_path(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _patch_chat_dependencies(monkeypatch, fail_stream=True)
    stream_snapshot = _load_snapshot("chat_stream.contract.json")

    resp = auth_client.post("/api/chat/stream", json={"message": "oi", "session_id": "contract-s3"})
    assert resp.status_code == 200

    events = _parse_sse_events(resp.text)
    sequence_errors = validate_chat_stream_sequence(events)
    assert not sequence_errors, f"invalid error-path SSE sequence: {sequence_errors}"

    event_specs = stream_snapshot["event_field_types"]
    for idx, event in enumerate(events):
        _assert_object_types(event, event_specs[event["type"]], label=f"chat_stream.error_event[{idx}]")

    assert events[-1]["type"] == "error"


def test_validate_chat_stream_sequence_rejects_invalid_order():
    invalid = [
        {"type": "start"},
        {"type": "done"},
    ]
    errors = validate_chat_stream_sequence(invalid)
    assert errors
    assert any("prior 'final'" in error or "requires exactly one 'final'" in error for error in errors)
