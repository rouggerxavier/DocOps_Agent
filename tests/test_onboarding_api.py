"""Onboarding API tests (Phase 1 backend).

Covers the contract in `docs/onboarding/spec.md`:
- `GET /api/onboarding/state` returns a full catalog and bootstrap state.
- `POST /api/onboarding/events` mutates state, enforces idempotency and
  validates unknown identifiers with 400.
- `POST /api/onboarding/reset` wipes progress and emits a telemetry event.
- Feature flag gating.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from docops.api.app import app
from docops.auth.dependencies import get_current_user
from docops.db.database import Base, get_db
from docops.db.models import User, UserOnboardingEventRecord, UserOnboardingStateRecord
from docops.onboarding import ONBOARDING_SCHEMA_VERSION, SECTIONS, total_step_count


_TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session():
    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield Session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def auth_client(db_session):
    fake_user = User(
        id=42,
        name="Tester",
        email="tester@example.com",
        password_hash="x",
        is_active=True,
        is_admin=False,
    )

    def _fake_auth():
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_auth
    client = TestClient(app)
    yield client, fake_user
    app.dependency_overrides.pop(get_current_user, None)


# ── GET /state ────────────────────────────────────────────────────────────────


def test_get_state_bootstraps_row_for_new_user(auth_client, db_session):
    client, user = auth_client

    resp = client.get("/api/onboarding/state")
    assert resp.status_code == 200

    body = resp.json()
    assert body["schema_version"] == ONBOARDING_SCHEMA_VERSION
    assert body["schema_upgrade_available"] is False
    assert body["tour"] == {
        "welcome_seen": False,
        "started": False,
        "completed": False,
        "skipped": False,
        "progress": {
            "completed": 0,
            "total": total_step_count(),
            "required_total": sum(
                1 for section in SECTIONS for step in section.steps if not step.premium
            ),
        },
    }
    assert body["last_step_seen"] is None
    assert len(body["sections"]) == len(SECTIONS)

    # Row persisted on first GET (lazy creation).
    with db_session() as db:
        records = db.query(UserOnboardingStateRecord).all()
        assert len(records) == 1
        assert records[0].user_id == user.id


def test_get_state_includes_catalog_shape(auth_client):
    client, _ = auth_client
    body = client.get("/api/onboarding/state").json()

    ingest = next(s for s in body["sections"] if s["id"] == "ingest")
    assert ingest["route"] == "/ingest"
    ingest_steps = {s["id"] for s in ingest["steps"]}
    assert {"ingest.types_overview", "ingest.first_upload"}.issubset(ingest_steps)

    first_upload = next(s for s in ingest["steps"] if s["id"] == "ingest.first_upload")
    assert first_upload["completion_mode"] == "auto"
    assert first_upload["next_hint"] == {"section": "chat", "step": "chat.first_question"}


# ── POST /events ──────────────────────────────────────────────────────────────


def test_post_event_step_completed_updates_state(auth_client):
    client, _ = auth_client

    resp = client.post(
        "/api/onboarding/events",
        json={"event_type": "step_completed", "step_id": "dashboard.explore", "section_id": "dashboard"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recorded"] is True
    assert body["state"]["tour"]["progress"]["completed"] == 1

    step = next(
        s
        for section in body["state"]["sections"]
        if section["id"] == "dashboard"
        for s in section["steps"]
        if s["id"] == "dashboard.explore"
    )
    assert step["completed_at"] is not None


def test_post_event_step_completed_is_idempotent(auth_client, db_session):
    client, user = auth_client
    payload = {"event_type": "step_completed", "step_id": "dashboard.explore", "section_id": "dashboard"}

    first = client.post("/api/onboarding/events", json=payload).json()
    assert first["recorded"] is True
    first_ts = next(
        s["completed_at"]
        for section in first["state"]["sections"]
        if section["id"] == "dashboard"
        for s in section["steps"]
        if s["id"] == "dashboard.explore"
    )

    second = client.post("/api/onboarding/events", json=payload).json()
    assert second["recorded"] is False
    second_ts = next(
        s["completed_at"]
        for section in second["state"]["sections"]
        if section["id"] == "dashboard"
        for s in section["steps"]
        if s["id"] == "dashboard.explore"
    )
    assert first_ts == second_ts

    with db_session() as db:
        events = db.query(UserOnboardingEventRecord).filter_by(user_id=user.id).all()
        assert len(events) == 1  # idempotent replay suppressed telemetry row


def test_post_event_welcome_shown_is_idempotent(auth_client):
    client, _ = auth_client
    first = client.post("/api/onboarding/events", json={"event_type": "welcome_shown"}).json()
    assert first["recorded"] is True
    assert first["state"]["tour"]["welcome_seen"] is True

    second = client.post("/api/onboarding/events", json={"event_type": "welcome_shown"}).json()
    assert second["recorded"] is False


def test_post_event_section_skipped_excludes_from_required(auth_client):
    client, _ = auth_client
    baseline = client.get("/api/onboarding/state").json()
    baseline_required = baseline["tour"]["progress"]["required_total"]

    # ingest has 2 non-premium steps.
    resp = client.post(
        "/api/onboarding/events",
        json={"event_type": "section_skipped", "section_id": "ingest"},
    )
    assert resp.status_code == 200
    state = resp.json()["state"]
    assert state["tour"]["progress"]["required_total"] == baseline_required - 2
    ingest = next(s for s in state["sections"] if s["id"] == "ingest")
    assert ingest["skipped"] is True


def test_post_event_tour_completed_when_all_required_done(auth_client):
    client, _ = auth_client

    # Complete every non-premium step.
    for section in SECTIONS:
        for step in section.steps:
            if step.premium:
                continue
            resp = client.post(
                "/api/onboarding/events",
                json={
                    "event_type": "step_completed",
                    "step_id": step.id,
                    "section_id": section.id,
                },
            )
            assert resp.status_code == 200

    final = client.get("/api/onboarding/state").json()
    assert final["tour"]["completed"] is True


def test_post_event_tour_reset_preserves_completions(auth_client):
    client, _ = auth_client
    client.post(
        "/api/onboarding/events",
        json={"event_type": "step_completed", "step_id": "dashboard.explore", "section_id": "dashboard"},
    )
    client.post(
        "/api/onboarding/events",
        json={"event_type": "section_skipped", "section_id": "chat"},
    )
    client.post("/api/onboarding/events", json={"event_type": "welcome_shown"})
    client.post("/api/onboarding/events", json={"event_type": "tour_skipped"})

    resp = client.post("/api/onboarding/events", json={"event_type": "tour_reset"})
    state = resp.json()["state"]

    assert state["tour"]["welcome_seen"] is False
    assert state["tour"]["skipped"] is False
    chat_section = next(s for s in state["sections"] if s["id"] == "chat")
    assert chat_section["skipped"] is False
    # step completion preserved
    dashboard_step = next(
        s
        for section in state["sections"]
        if section["id"] == "dashboard"
        for s in section["steps"]
        if s["id"] == "dashboard.explore"
    )
    assert dashboard_step["completed_at"] is not None


def test_post_event_rejects_unknown_event_type(auth_client):
    client, _ = auth_client
    resp = client.post("/api/onboarding/events", json={"event_type": "not_a_real_event"})
    assert resp.status_code == 400


def test_post_event_rejects_unknown_step(auth_client):
    client, _ = auth_client
    resp = client.post(
        "/api/onboarding/events",
        json={"event_type": "step_completed", "step_id": "does.not.exist"},
    )
    assert resp.status_code == 400


def test_post_event_rejects_unknown_section(auth_client):
    client, _ = auth_client
    resp = client.post(
        "/api/onboarding/events",
        json={"event_type": "section_skipped", "section_id": "ghost"},
    )
    assert resp.status_code == 400


def test_post_event_step_seen_updates_last_step(auth_client):
    client, _ = auth_client
    resp = client.post(
        "/api/onboarding/events",
        json={"event_type": "step_seen", "step_id": "chat.first_question"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"]["last_step_seen"] == "chat.first_question"


def test_upgrade_intent_records_telemetry_without_state_change(auth_client, db_session):
    client, user = auth_client
    resp = client.post(
        "/api/onboarding/events",
        json={
            "event_type": "upgrade_intent_from_onboarding",
            "step_id": "chat.memory",
            "section_id": "chat",
            "metadata": {"cta": "memory"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["recorded"] is True

    with db_session() as db:
        events = db.query(UserOnboardingEventRecord).filter_by(user_id=user.id).all()
        assert len(events) == 1
        assert events[0].event_type == "upgrade_intent_from_onboarding"
        assert events[0].event_metadata == {"cta": "memory"}


# ── POST /reset ───────────────────────────────────────────────────────────────


def test_reset_wipes_everything(auth_client, db_session):
    client, user = auth_client
    client.post(
        "/api/onboarding/events",
        json={"event_type": "step_completed", "step_id": "dashboard.explore", "section_id": "dashboard"},
    )
    client.post("/api/onboarding/events", json={"event_type": "tour_skipped"})

    resp = client.post("/api/onboarding/reset")
    assert resp.status_code == 200
    state = resp.json()
    assert state["tour"]["skipped"] is False
    assert state["tour"]["progress"]["completed"] == 0
    assert all(
        s["completed_at"] is None
        for section in state["sections"]
        for s in section["steps"]
    )

    with db_session() as db:
        events = db.query(UserOnboardingEventRecord).filter_by(
            user_id=user.id, event_type="tour_reset"
        ).all()
        assert len(events) == 1
        assert events[0].event_metadata == {"variant": "hard"}


# ── Feature flag ──────────────────────────────────────────────────────────────


def test_feature_flag_disabled_returns_404(auth_client, monkeypatch):
    client, _ = auth_client
    monkeypatch.setenv("FEATURE_FLAGS", "onboarding_enabled=false")

    for method, path, body in (
        ("get", "/api/onboarding/state", None),
        ("post", "/api/onboarding/events", {"event_type": "welcome_shown"}),
        ("post", "/api/onboarding/reset", None),
    ):
        if method == "get":
            resp = client.get(path)
        else:
            resp = client.post(path, json=body)
        assert resp.status_code == 404, f"{method.upper()} {path} should be 404 when flag off"
