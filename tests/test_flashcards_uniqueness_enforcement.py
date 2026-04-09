from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
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
from docops.db.models import FlashcardDeck, FlashcardItem


@pytest.fixture
def flashcards_client():
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
        user_db = crud.create_user(db, "Uniq Tester", "uniq@test.com", "hash")
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


def test_create_flashcard_deck_skips_repeated_fronts(flashcards_client):
    _, session_factory, user = flashcards_client

    with session_factory() as db:
        deck = crud.create_flashcard_deck(
            db,
            user_id=user.id,
            title="Deck Teste",
            source_doc="Aula.pdf",
            cards=[
                {"front": "Quais sao os indicadores de overfitting?", "back": "Gap treino-validacao.", "difficulty": "facil"},
                {"front": "  QUAIS SAO OS INDICADORES DE OVERFITTING ?  ", "back": "Mesmo tema.", "difficulty": "media"},
                {"front": "Como reduzir overfitting?", "back": "Regularizacao e validacao cruzada.", "difficulty": "media"},
            ],
        )
        deck_id = deck.id

    with session_factory() as db:
        persisted = db.query(FlashcardItem).filter(FlashcardItem.deck_id == deck_id).all()
        assert len(persisted) == 2
        fronts = [item.front for item in persisted]
        assert "Como reduzir overfitting?" in fronts


def test_get_deck_auto_repairs_existing_duplicate_cards(flashcards_client):
    client, session_factory, user = flashcards_client

    with session_factory() as db:
        deck = FlashcardDeck(user_id=user.id, title="Deck legado", source_doc="Legado.pdf")
        db.add(deck)
        db.flush()
        db.add(
            FlashcardItem(
                deck_id=deck.id,
                front="Quais sao os indicadores formais de overfitting?",
                back="Erro baixo em treino e alto em validacao/teste.",
                difficulty="facil",
            )
        )
        db.add(
            FlashcardItem(
                deck_id=deck.id,
                front="Quais sao os indicadores formais de overfitting?",
                back="Mesmo card repetido.",
                difficulty="facil",
            )
        )
        db.add(
            FlashcardItem(
                deck_id=deck.id,
                front="Como mitigar overfitting?",
                back="Use regularizacao, early stopping e mais dados.",
                difficulty="media",
            )
        )
        db.commit()
        deck_id = int(deck.id)

    resp = client.get(f"/api/flashcards/{deck_id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["cards"]) == 2
    assert len({card["front"] for card in payload["cards"]}) == 2

    with session_factory() as db:
        persisted = db.query(FlashcardItem).filter(FlashcardItem.deck_id == deck_id).all()
        assert len(persisted) == 2
