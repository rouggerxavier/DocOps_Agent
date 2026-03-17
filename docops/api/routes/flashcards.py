"""Rotas de flashcards — /api/flashcards."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger

logger = get_logger("docops.api.flashcards")
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CardSchema(BaseModel):
    id: int
    front: str
    back: str
    ease: int
    next_review: Optional[datetime]

    class Config:
        from_attributes = True


class DeckResponse(BaseModel):
    id: int
    title: str
    source_doc: Optional[str]
    created_at: datetime
    cards: list[CardSchema]

    class Config:
        from_attributes = True


class DeckListItem(BaseModel):
    id: int
    title: str
    source_doc: Optional[str]
    card_count: int
    created_at: datetime


class GenerateRequest(BaseModel):
    doc_name: str = Field(min_length=1)
    num_cards: int = Field(default=10, ge=3, le=30)


class ReviewRequest(BaseModel):
    card_id: int
    ease: int = Field(ge=0, le=3)


# ── Geração de flashcards via LLM ────────────────────────────────────────────

FLASHCARD_PROMPT = """\
Você é um especialista em criar flashcards para revisão espaçada.
Com base no conteúdo abaixo, gere exatamente {num_cards} flashcards.
Cada flashcard deve ter uma pergunta objetiva (front) e uma resposta concisa (back).

Regras:
- As perguntas devem cobrir os conceitos mais importantes do texto.
- Varie entre definições, fatos, relações e aplicações.
- Respostas devem ser curtas (1-3 frases).
- Retorne APENAS um JSON array no formato: [{{"front": "...", "back": "..."}}]
- Sem markdown, sem texto extra, APENAS o JSON array.

Conteúdo:
{content}
"""


def _generate_cards(doc_name: str, doc_id: str, user_id: int, num_cards: int) -> list[dict]:
    from docops.rag.retriever import retrieve_for_doc
    from docops.config import config
    import google.generativeai as genai

    chunks = retrieve_for_doc(doc_name, query="conteúdo principal do documento", doc_id=doc_id, user_id=user_id, top_k=30)
    if not chunks:
        raise HTTPException(status_code=404, detail="Nenhum chunk encontrado para este documento.")

    content = "\n\n".join(
        c.page_content[:800] for c in chunks[:20]
    )

    genai.configure(api_key=config.gemini_api_key)
    model = genai.GenerativeModel(config.gemini_model)
    prompt = FLASHCARD_PROMPT.format(num_cards=num_cards, content=content[:12000])

    response = model.generate_content(prompt)
    text = response.text.strip()

    # Limpa possíveis wrappers markdown
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        cards = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Falha ao parsear flashcards: %s", text[:200])
        raise HTTPException(status_code=500, detail="Erro ao gerar flashcards. Tente novamente.")

    if not isinstance(cards, list):
        raise HTTPException(status_code=500, detail="Formato de resposta inesperado.")

    return [{"front": c["front"], "back": c["back"]} for c in cards if "front" in c and "back" in c]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/flashcards", response_model=list[DeckListItem])
def list_decks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    decks = crud.list_flashcard_decks_for_user(db, current_user.id)
    return [
        DeckListItem(
            id=d.id,
            title=d.title,
            source_doc=d.source_doc,
            card_count=len(d.cards),
            created_at=d.created_at,
        )
        for d in decks
    ]


@router.get("/flashcards/{deck_id}", response_model=DeckResponse)
def get_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deck = crud.get_flashcard_deck_by_user_and_id(db, current_user.id, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck não encontrado.")
    return deck


@router.post("/flashcards/generate", response_model=DeckResponse)
async def generate_deck(
    payload: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from docops.services.ownership import require_user_document
    doc_record = require_user_document(db, current_user.id, payload.doc_name)

    cards = await asyncio.to_thread(
        _generate_cards,
        doc_record.file_name,
        doc_record.doc_id,
        current_user.id,
        payload.num_cards,
    )

    deck = crud.create_flashcard_deck(
        db,
        user_id=current_user.id,
        title=f"Flashcards — {doc_record.file_name}",
        source_doc=doc_record.file_name,
        cards=cards,
    )
    return deck


@router.post("/flashcards/review")
def review_card(
    payload: ReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = crud.update_flashcard_ease(db, payload.card_id, payload.ease)
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado.")
    return {"status": "ok", "next_review": card.next_review.isoformat() if card.next_review else None}


@router.delete("/flashcards/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deck = crud.get_flashcard_deck_by_user_and_id(db, current_user.id, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck não encontrado.")
    crud.delete_flashcard_deck(db, deck)
