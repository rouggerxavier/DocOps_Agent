from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from docops.api.app import app
from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import Base, get_db


@pytest.fixture
def batch_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_auth_override = app.dependency_overrides.get(get_current_user)

    def _override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    with Session() as db:
        user_db = crud.create_user(db, "Batch Tester", "batch@test.com", "hash")
        user = SimpleNamespace(
            id=int(user_db.id),
            name=str(user_db.name),
            email=str(user_db.email),
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)

    try:
        yield client, Session, user
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

        if previous_auth_override is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_auth_override


def _seed_docs(session_factory, user_id: int, names: list[str]):
    with session_factory() as db:
        for idx, file_name in enumerate(names, start=1):
            crud.create_document_record(
                db,
                user_id=user_id,
                doc_id=f"doc-{idx}",
                file_name=file_name,
                source_path=f"/docs/{file_name}",
                storage_path=f"/docs/{file_name}",
                file_type="pdf",
                chunk_count=3,
            )


def _fake_cards(doc_name: str, num_cards: int):
    return [
        {
            "front": f"{doc_name} - pergunta {idx}",
            "back": f"{doc_name} - resposta {idx}",
            "difficulty": "media",
        }
        for idx in range(1, num_cards + 1)
    ]


def test_generate_flashcards_batch_all_docs_creates_one_deck_per_document(batch_client, monkeypatch):
    client, session_factory, user = batch_client
    _seed_docs(session_factory, user.id, ["Aula 1.pdf", "Aula 2.pdf"])

    monkeypatch.setattr(
        "docops.api.routes.flashcards._generate_cards",
        lambda doc_name, doc_id, user_id, num_cards, content_filter="", difficulty_mode="any", difficulty_custom=None: _fake_cards(doc_name, num_cards),
    )

    resp = client.post(
        "/api/flashcards/generate-batch",
        json={
            "all_docs": True,
            "num_cards": 2,
            "difficulty_mode": "any",
            "content_filter": "",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["requested_docs"] == 2
    assert data["created"] == 2
    assert data["failed"] == 0
    assert len(data["items"]) == 2
    assert all(item["status"] == "created" for item in data["items"])
    assert {item["source_doc"] for item in data["items"]} == {"Aula 1.pdf", "Aula 2.pdf"}


def test_generate_flashcards_batch_isolates_document_failures(batch_client, monkeypatch):
    client, session_factory, user = batch_client
    _seed_docs(session_factory, user.id, ["Aula 1.pdf", "Aula 2.pdf", "Aula 3.pdf"])

    def fake_generate_cards(doc_name, doc_id, user_id, num_cards, content_filter="", difficulty_mode="any", difficulty_custom=None):
        if doc_name == "Aula 2.pdf":
            raise HTTPException(status_code=502, detail="falha controlada")
        return _fake_cards(doc_name, num_cards)

    monkeypatch.setattr("docops.api.routes.flashcards._generate_cards", fake_generate_cards)

    resp = client.post(
        "/api/flashcards/generate-batch",
        json={
            "doc_names": ["Aula 1.pdf", "Aula 2.pdf", "Aula 3.pdf"],
            "num_cards": 1,
            "difficulty_mode": "any",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["requested_docs"] == 3
    assert data["created"] == 2
    assert data["failed"] == 1

    failures = [item for item in data["items"] if item["status"] == "failed"]
    assert len(failures) == 1
    assert failures[0]["source_doc"] == "Aula 2.pdf"
    assert "falha controlada" in failures[0]["error"]


def test_generate_flashcards_batch_reports_missing_documents(batch_client, monkeypatch):
    client, session_factory, user = batch_client
    _seed_docs(session_factory, user.id, ["Aula 1.pdf"])

    monkeypatch.setattr(
        "docops.api.routes.flashcards._generate_cards",
        lambda doc_name, doc_id, user_id, num_cards, content_filter="", difficulty_mode="any", difficulty_custom=None: _fake_cards(doc_name, num_cards),
    )

    resp = client.post(
        "/api/flashcards/generate-batch",
        json={
            "doc_names": ["Aula 1.pdf", "Nao existe.pdf"],
            "num_cards": 1,
            "difficulty_mode": "any",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["requested_docs"] == 2
    assert data["created"] == 1
    assert data["failed"] == 1

    missing = [item for item in data["items"] if item["status"] == "failed"]
    assert len(missing) == 1
    assert missing[0]["requested_doc_name"] == "Nao existe.pdf"
    assert missing[0]["source_doc"] is None
    assert "Documento nao encontrado" in missing[0]["error"]


def test_generate_flashcards_batch_rejects_ambiguous_payload(batch_client):
    client, _, _ = batch_client

    resp = client.post(
        "/api/flashcards/generate-batch",
        json={
            "all_docs": True,
            "doc_names": ["Aula 1.pdf"],
            "num_cards": 1,
        },
    )

    assert resp.status_code == 422
    assert "all_docs=true ou doc_names" in resp.json()["detail"]
