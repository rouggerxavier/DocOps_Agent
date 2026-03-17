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
    difficulty: str  # facil, media, dificil
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
    num_cards: int = Field(default=10, ge=1, le=60)
    content_filter: str = Field(default="", description="Filtro opcional de conteúdo específico do documento")
    difficulty_mode: str = Field(default="any", description="any | only_facil | only_media | only_dificil | custom")
    difficulty_custom: Optional[dict[str, int]] = Field(default=None, description="{'facil': N, 'media': N, 'dificil': N} — usado só no modo custom")


class ReviewRequest(BaseModel):
    card_id: int
    ease: int = Field(ge=0, le=3)


class UpdateDifficultyRequest(BaseModel):
    difficulty: str


class EvaluateAnswerRequest(BaseModel):
    user_answer: str = Field(min_length=1)


class EvaluateAnswerResponse(BaseModel):
    verdict: str   # "correta" | "parcial" | "incorreta"
    feedback: str
    highlight: str


# ── Geração de flashcards via LLM ────────────────────────────────────────────

FLASHCARD_EVAL_PROMPT = """\
Você é um avaliador pedagógico de flashcards.

Pergunta: {front}
Resposta correta: {back}
Resposta do estudante: {user_answer}

Avalie a resposta do estudante de forma construtiva e objetiva.
Retorne APENAS um JSON válido (sem markdown, sem texto extra):
{{"verdict": "correta" | "parcial" | "incorreta", "feedback": "Avaliação em 2-4 frases: o que acertou, o que errou e como melhorar.", "highlight": "Principal ponto a melhorar ou reforçar (1 frase curta)."}}

Critérios:
- "correta": essência correta, mesmo com palavras diferentes
- "parcial": acertou parte, mas faltou algo importante ou há imprecisões
- "incorreta": resposta errada, muito incompleta ou irrelevante
"""


FLASHCARD_PROMPT = """\
Você é um especialista em criar flashcards para revisão espaçada.
Com base no conteúdo abaixo, gere exatamente {num_cards} flashcards.
Cada flashcard deve ter uma pergunta objetiva (front), uma resposta concisa (back) e uma classificação de dificuldade (difficulty).
{filter_instruction}{difficulty_instruction}
Regras:
- As perguntas devem cobrir os conceitos mais importantes do texto.
- Varie entre definições, fatos, relações e aplicações.
- Respostas devem ser curtas (1-3 frases).
- O campo "difficulty" deve ser: "facil" (fato direto/definição simples), "media" (requer compreensão/conexão) ou "dificil" (requer análise/aplicação avançada).
- Retorne APENAS um JSON array no formato: [{{"front": "...", "back": "...", "difficulty": "facil|media|dificil"}}]
- Sem markdown, sem texto extra, APENAS o JSON array.

Conteúdo:
{content}
"""


def _build_difficulty_instruction(mode: str, custom: dict | None) -> str:
    if mode == "only_facil":
        return '\nDificuldade: gere TODOS os cards como "facil" (definições simples, fatos diretos, memorização direta).\n'
    if mode == "only_media":
        return '\nDificuldade: gere TODOS os cards como "media" (requerem compreensão ou conexão entre conceitos).\n'
    if mode == "only_dificil":
        return '\nDificuldade: gere TODOS os cards como "dificil" (análise crítica, aplicação avançada, síntese).\n'
    if mode == "custom" and custom:
        n_f = custom.get("facil", 0)
        n_m = custom.get("media", 0)
        n_d = custom.get("dificil", 0)
        return (
            f'\nDistribuição OBRIGATÓRIA de dificuldade: '
            f'{n_f} card(s) "facil", {n_m} card(s) "media", {n_d} card(s) "dificil". '
            f'Total: {n_f + n_m + n_d} cards. Respeite exatamente essa distribuição.\n'
        )
    return ""


def _generate_cards(
    doc_name: str,
    doc_id: str,
    user_id: int,
    num_cards: int,
    content_filter: str = "",
    difficulty_mode: str = "any",
    difficulty_custom: dict | None = None,
) -> list[dict]:
    from docops.rag.retriever import retrieve_for_doc
    from docops.config import config
    from google import genai

    query = content_filter.strip() if content_filter.strip() else "conteúdo principal do documento"
    chunks = retrieve_for_doc(doc_name, query=query, doc_id=doc_id, user_id=user_id, top_k=30)
    if not chunks:
        raise HTTPException(status_code=404, detail="Nenhum chunk encontrado para este documento.")

    content = "\n\n".join(c.page_content[:800] for c in chunks[:20])

    filter_instruction = ""
    if content_filter.strip():
        filter_instruction = f'\nFoco: gere flashcards APENAS sobre "{content_filter.strip()}". Ignore conteúdo não relacionado.\n'

    difficulty_instruction = _build_difficulty_instruction(difficulty_mode, difficulty_custom)

    client = genai.Client(api_key=config.gemini_api_key)
    prompt = FLASHCARD_PROMPT.format(
        num_cards=num_cards,
        content=content[:12000],
        filter_instruction=filter_instruction,
        difficulty_instruction=difficulty_instruction,
    )

    response = client.models.generate_content(model=config.gemini_model, contents=prompt)
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

    valid_difficulties = {"facil", "media", "dificil"}
    return [
        {
            "front": c["front"],
            "back": c["back"],
            "difficulty": c.get("difficulty", "media") if c.get("difficulty", "media") in valid_difficulties else "media",
        }
        for c in cards
        if "front" in c and "back" in c
    ]


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

    # No modo custom, o num_cards é a soma da distribuição
    num_cards = payload.num_cards
    if payload.difficulty_mode == "custom" and payload.difficulty_custom:
        num_cards = sum(payload.difficulty_custom.values())
        if num_cards < 1:
            raise HTTPException(status_code=422, detail="A distribuição personalizada deve ter ao menos 1 card.")

    cards = await asyncio.to_thread(
        _generate_cards,
        doc_record.file_name,
        doc_record.doc_id,
        current_user.id,
        num_cards,
        payload.content_filter,
        payload.difficulty_mode,
        payload.difficulty_custom,
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
    # Verifica ownership antes de atualizar
    owned = crud.get_flashcard_item_by_user(db, payload.card_id, user_id=current_user.id)
    if not owned:
        raise HTTPException(status_code=404, detail="Card não encontrado.")
    card = crud.update_flashcard_ease(db, payload.card_id, payload.ease)
    return {"status": "ok", "next_review": card.next_review.isoformat() if card.next_review else None}


@router.post("/flashcards/card/{card_id}/evaluate", response_model=EvaluateAnswerResponse)
def evaluate_answer(
    card_id: int,
    payload: EvaluateAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = crud.get_flashcard_item_by_user(db, card_id, user_id=current_user.id)
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado.")

    from docops.config import config
    from google import genai

    client = genai.Client(api_key=config.gemini_api_key)
    prompt = FLASHCARD_EVAL_PROMPT.format(
        front=card.front,
        back=card.back,
        user_answer=payload.user_answer,
    )
    response = client.models.generate_content(model=config.gemini_model, contents=prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Falha ao parsear avaliação: %s", text[:200])
        raise HTTPException(status_code=500, detail="Erro ao avaliar resposta. Tente novamente.")

    valid_verdicts = {"correta", "parcial", "incorreta"}
    verdict = data.get("verdict", "parcial")
    if verdict not in valid_verdicts:
        verdict = "parcial"

    return EvaluateAnswerResponse(
        verdict=verdict,
        feedback=data.get("feedback", ""),
        highlight=data.get("highlight", ""),
    )


@router.put("/flashcards/card/{card_id}/difficulty")
def update_card_difficulty(
    card_id: int,
    payload: UpdateDifficultyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid = {"facil", "media", "dificil"}
    if payload.difficulty not in valid:
        raise HTTPException(status_code=422, detail="Dificuldade inválida.")
    card = crud.update_flashcard_difficulty(db, card_id, payload.difficulty, user_id=current_user.id)
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado.")
    return {"status": "ok", "difficulty": card.difficulty}


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
