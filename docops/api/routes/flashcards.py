"""Flashcard routes exposed under /api/flashcards."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger

logger = get_logger("docops.api.flashcards")
router = APIRouter()

VALID_DIFFICULTIES = {"facil", "media", "dificil"}
FLASHCARD_GENERATION_MAX_ATTEMPTS = 3


class CardSchema(BaseModel):
    id: int
    front: str
    back: str
    difficulty: str
    ease: int
    next_review: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class DeckResponse(BaseModel):
    id: int
    title: str
    source_doc: Optional[str]
    created_at: datetime
    cards: list[CardSchema]

    model_config = ConfigDict(from_attributes=True)


class DeckListItem(BaseModel):
    id: int
    title: str
    source_doc: Optional[str]
    card_count: int
    created_at: datetime


class GenerateRequest(BaseModel):
    doc_name: str = Field(min_length=1)
    num_cards: int = Field(default=10, ge=1, le=60)
    content_filter: str = Field(default="", description="Optional document content filter")
    difficulty_mode: str = Field(default="any", description="any | only_facil | only_media | only_dificil | custom")
    difficulty_custom: Optional[dict[str, int]] = Field(
        default=None,
        description="{'facil': N, 'media': N, 'dificil': N} for custom mode",
    )


class ReviewRequest(BaseModel):
    card_id: int
    ease: int = Field(ge=0, le=3)


class UpdateDifficultyRequest(BaseModel):
    difficulty: str


class EvaluateAnswerRequest(BaseModel):
    user_answer: str = Field(min_length=1)


class EvaluateAnswerResponse(BaseModel):
    verdict: str
    feedback: str
    highlight: str


FLASHCARD_EVAL_PROMPT = """\
Voce e um avaliador pedagogico de flashcards.

Pergunta: {front}
Resposta correta: {back}
Resposta do estudante: {user_answer}

Avalie a resposta do estudante de forma construtiva e objetiva.
Retorne APENAS um JSON valido (sem markdown, sem texto extra):
{{"verdict": "correta" | "parcial" | "incorreta", "feedback": "Avaliacao em 2-4 frases: o que acertou, o que errou e como melhorar.", "highlight": "Principal ponto a melhorar ou reforcar (1 frase curta)."}}

Criterios:
- "correta": essencia correta, mesmo com palavras diferentes
- "parcial": acertou parte, mas faltou algo importante ou ha imprecisoes
- "incorreta": resposta errada, muito incompleta ou irrelevante
"""


FLASHCARD_PROMPT = """\
Voce e um especialista em criar flashcards para revisao espacada.
Com base no conteudo abaixo, gere exatamente {num_cards} flashcards.
Cada flashcard deve ter uma pergunta objetiva (front), uma resposta concisa (back) e uma classificacao de dificuldade (difficulty).
{filter_instruction}{difficulty_instruction}{uniqueness_instruction}
Regras:
- As perguntas devem cobrir os conceitos mais importantes do texto.
- Varie entre definicoes, fatos, relacoes e aplicacoes.
- Respostas devem ser curtas (1-3 frases).
- O campo "difficulty" deve ser: "facil" (fato direto/definicao simples), "media" (requer compreensao/conexao) ou "dificil" (requer analise/aplicacao avancada).
- Cada pergunta deve ser unica. Nao repita a mesma pergunta, conceito ou formulacao com palavras ligeiramente diferentes.
- Retorne APENAS um JSON array no formato: [{{"front": "...", "back": "...", "difficulty": "facil|media|dificil"}}]
- Sem markdown, sem texto extra, APENAS o JSON array.

Conteudo:
{content}
"""


def _build_difficulty_instruction(mode: str, custom: dict | None) -> str:
    if mode == "only_facil":
        return '\nDificuldade: gere TODOS os cards como "facil" (definicoes simples, fatos diretos, memorizacao direta).\n'
    if mode == "only_media":
        return '\nDificuldade: gere TODOS os cards como "media" (requerem compreensao ou conexao entre conceitos).\n'
    if mode == "only_dificil":
        return '\nDificuldade: gere TODOS os cards como "dificil" (analise critica, aplicacao avancada, sintese).\n'
    if mode == "custom" and custom:
        n_f = int(custom.get("facil", 0))
        n_m = int(custom.get("media", 0))
        n_d = int(custom.get("dificil", 0))
        return (
            '\nDistribuicao OBRIGATORIA de dificuldade: '
            f'{n_f} card(s) "facil", {n_m} card(s) "media", {n_d} card(s) "dificil". '
            f"Total: {n_f + n_m + n_d} cards. Respeite exatamente essa distribuicao.\n"
        )
    return ""


def _build_target_difficulty_counts(mode: str, num_cards: int, custom: dict | None) -> dict[str, int] | None:
    if mode == "custom":
        return {
            "facil": max(0, int((custom or {}).get("facil", 0))),
            "media": max(0, int((custom or {}).get("media", 0))),
            "dificil": max(0, int((custom or {}).get("dificil", 0))),
        }
    if mode == "only_facil":
        return {"facil": num_cards, "media": 0, "dificil": 0}
    if mode == "only_media":
        return {"facil": 0, "media": num_cards, "dificil": 0}
    if mode == "only_dificil":
        return {"facil": 0, "media": 0, "dificil": num_cards}
    return None


def _build_difficulty_instruction_from_counts(target_counts: dict[str, int] | None) -> str:
    if not target_counts:
        return ""

    non_zero = {key: value for key, value in target_counts.items() if value > 0}
    if not non_zero:
        return ""

    if len(non_zero) == 1:
        difficulty, amount = next(iter(non_zero.items()))
        return f'\nDificuldade: gere exatamente {amount} card(s), todos como "{difficulty}".\n'

    return (
        '\nDistribuicao OBRIGATORIA de dificuldade: '
        f'{target_counts.get("facil", 0)} card(s) "facil", '
        f'{target_counts.get("media", 0)} card(s) "media", '
        f'{target_counts.get("dificil", 0)} card(s) "dificil". '
        f"Total: {sum(target_counts.values())} cards. Respeite exatamente essa distribuicao.\n"
    )


def _normalize_card_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return normalized.strip()


def _sanitize_card(raw_card: object) -> dict | None:
    if not isinstance(raw_card, dict):
        return None

    front = str(raw_card.get("front", "")).strip()
    back = str(raw_card.get("back", "")).strip()
    if not front or not back:
        return None

    difficulty = str(raw_card.get("difficulty", "media")).strip().casefold()
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "media"

    return {
        "front": front,
        "back": back,
        "difficulty": difficulty,
    }


def _dedupe_cards(cards: list[object], seen_fronts: set[str] | None = None) -> list[dict]:
    accepted: list[dict] = []
    seen_front_keys = set(seen_fronts or set())
    seen_pairs: set[tuple[str, str]] = set()

    for raw_card in cards:
        card = _sanitize_card(raw_card)
        if not card:
            continue

        front_key = _normalize_card_text(card["front"])
        back_key = _normalize_card_text(card["back"])
        pair_key = (front_key, back_key)

        if not front_key or front_key in seen_front_keys or pair_key in seen_pairs:
            continue

        seen_front_keys.add(front_key)
        seen_pairs.add(pair_key)
        accepted.append(card)

    return accepted


def _count_cards_by_difficulty(cards: list[dict]) -> dict[str, int]:
    counts = {difficulty: 0 for difficulty in VALID_DIFFICULTIES}
    for card in cards:
        difficulty = card.get("difficulty", "media")
        if difficulty in counts:
            counts[difficulty] += 1
    return counts


def _missing_target_counts(cards: list[dict], target_counts: dict[str, int] | None) -> dict[str, int] | None:
    if target_counts is None:
        return None

    current_counts = _count_cards_by_difficulty(cards)
    return {
        difficulty: max(0, target_counts.get(difficulty, 0) - current_counts.get(difficulty, 0))
        for difficulty in VALID_DIFFICULTIES
    }


def _select_cards_for_targets(cards: list[dict], target_counts: dict[str, int]) -> list[dict]:
    selected: list[dict] = []
    remaining = dict(target_counts)

    for card in cards:
        difficulty = card["difficulty"]
        if remaining.get(difficulty, 0) <= 0:
            continue
        selected.append(card)
        remaining[difficulty] -= 1

    return selected


def _build_uniqueness_instruction(excluded_fronts: list[str]) -> str:
    if not excluded_fronts:
        return "\nUnicidade: todas as perguntas devem ser diferentes entre si.\n"

    sample = "\n".join(f"- {front}" for front in excluded_fronts[:20])
    return (
        "\nUnicidade: gere perguntas novas, sem repetir nem parafrasear as perguntas abaixo.\n"
        "Perguntas proibidas nesta tentativa:\n"
        f"{sample}\n"
    )


def _parse_flashcard_response(text: str) -> list[object]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        cards = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Falha ao parsear flashcards: %s", cleaned[:200])
        raise HTTPException(status_code=500, detail="Erro ao gerar flashcards. Tente novamente.")

    if not isinstance(cards, list):
        raise HTTPException(status_code=500, detail="Formato de resposta inesperado.")

    return cards


def _request_flashcard_batch(
    *,
    client,
    model: str,
    content: str,
    num_cards: int,
    filter_instruction: str,
    difficulty_instruction: str,
    excluded_fronts: list[str],
) -> list[object]:
    prompt = FLASHCARD_PROMPT.format(
        num_cards=num_cards,
        content=content[:12000],
        filter_instruction=filter_instruction,
        difficulty_instruction=difficulty_instruction,
        uniqueness_instruction=_build_uniqueness_instruction(excluded_fronts),
    )
    response = client.models.generate_content(model=model, contents=prompt)
    return _parse_flashcard_response(getattr(response, "text", ""))


def _collect_flashcards(fetch_batch, *, total_cards: int, target_counts: dict[str, int] | None) -> list[dict]:
    accepted: list[dict] = []
    seen_fronts: set[str] = set()

    for _attempt in range(FLASHCARD_GENERATION_MAX_ATTEMPTS):
        missing_total = total_cards - len(accepted)
        if missing_total <= 0:
            break

        missing_targets = _missing_target_counts(accepted, target_counts)
        difficulty_instruction = _build_difficulty_instruction_from_counts(missing_targets)
        excluded_fronts = [card["front"] for card in accepted]
        batch = fetch_batch(
            num_cards=missing_total,
            difficulty_instruction=difficulty_instruction,
            excluded_fronts=excluded_fronts,
        )

        prepared_cards = _dedupe_cards(batch, seen_fronts=seen_fronts)
        seen_fronts.update(_normalize_card_text(card["front"]) for card in prepared_cards)

        if target_counts is None:
            accepted.extend(prepared_cards[:missing_total])
            continue

        accepted.extend(_select_cards_for_targets(prepared_cards, missing_targets or {}))

    if target_counts is not None:
        missing_targets = _missing_target_counts(accepted, target_counts) or {}
        if any(missing_targets.values()):
            details = ", ".join(
                f"{difficulty}: faltaram {amount}"
                for difficulty, amount in missing_targets.items()
                if amount > 0
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Nao foi possivel gerar flashcards unicos com a distribuicao pedida "
                    f"({details}). Tente reduzir a quantidade ou ampliar o escopo."
                ),
            )

    if len(accepted) < total_cards:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Nao foi possivel gerar {total_cards} flashcards unicos. "
                "Tente reduzir a quantidade ou ampliar o escopo."
            ),
        )

    return accepted[:total_cards]


def _generate_cards(
    doc_name: str,
    doc_id: str,
    user_id: int,
    num_cards: int,
    content_filter: str = "",
    difficulty_mode: str = "any",
    difficulty_custom: dict | None = None,
) -> list[dict]:
    from docops.config import config
    from docops.rag.retriever import retrieve_for_doc
    from google import genai

    query = content_filter.strip() if content_filter.strip() else "conteudo principal do documento"
    chunks = retrieve_for_doc(doc_name, query=query, doc_id=doc_id, user_id=user_id, top_k=30)
    if not chunks:
        raise HTTPException(status_code=404, detail="Nenhum chunk encontrado para este documento.")

    content = "\n\n".join(chunk.page_content[:800] for chunk in chunks[:20])

    filter_instruction = ""
    if content_filter.strip():
        filter_instruction = (
            f'\nFoco: gere flashcards APENAS sobre "{content_filter.strip()}". '
            "Ignore conteudo nao relacionado.\n"
        )

    target_counts = _build_target_difficulty_counts(difficulty_mode, num_cards, difficulty_custom)
    initial_difficulty_instruction = _build_difficulty_instruction(difficulty_mode, difficulty_custom)

    client = genai.Client(api_key=config.gemini_api_key)

    def _fetch_batch(*, num_cards: int, difficulty_instruction: str, excluded_fronts: list[str]) -> list[object]:
        effective_instruction = difficulty_instruction or initial_difficulty_instruction
        return _request_flashcard_batch(
            client=client,
            model=config.gemini_model,
            content=content,
            num_cards=num_cards,
            filter_instruction=filter_instruction,
            difficulty_instruction=effective_instruction,
            excluded_fronts=excluded_fronts,
        )

    return _collect_flashcards(
        _fetch_batch,
        total_cards=num_cards,
        target_counts=target_counts,
    )


@router.get("/flashcards", response_model=list[DeckListItem])
def list_decks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    decks = crud.list_flashcard_decks_for_user(db, current_user.id)
    return [
        DeckListItem(
            id=deck.id,
            title=deck.title,
            source_doc=deck.source_doc,
            card_count=len(deck.cards),
            created_at=deck.created_at,
        )
        for deck in decks
    ]


@router.get("/flashcards/{deck_id}", response_model=DeckResponse)
def get_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deck = crud.get_flashcard_deck_by_user_and_id(db, current_user.id, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck nao encontrado.")
    return deck


@router.post("/flashcards/generate", response_model=DeckResponse)
async def generate_deck(
    payload: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from docops.services.ownership import require_user_document

    doc_record = require_user_document(db, current_user.id, payload.doc_name)

    num_cards = payload.num_cards
    if payload.difficulty_mode == "custom" and payload.difficulty_custom:
        num_cards = sum(payload.difficulty_custom.values())
        if num_cards < 1:
            raise HTTPException(status_code=422, detail="A distribuicao personalizada deve ter ao menos 1 card.")

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
        title=f"Flashcards - {doc_record.file_name}",
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
    owned = crud.get_flashcard_item_by_user(db, payload.card_id, user_id=current_user.id)
    if not owned:
        raise HTTPException(status_code=404, detail="Card nao encontrado.")

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
        raise HTTPException(status_code=404, detail="Card nao encontrado.")

    from docops.config import config
    from google import genai

    client = genai.Client(api_key=config.gemini_api_key)
    prompt = FLASHCARD_EVAL_PROMPT.format(
        front=card.front,
        back=card.back,
        user_answer=payload.user_answer,
    )
    response = client.models.generate_content(model=config.gemini_model, contents=prompt)
    text = getattr(response, "text", "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Falha ao parsear avaliacao: %s", text[:200])
        raise HTTPException(status_code=500, detail="Erro ao avaliar resposta. Tente novamente.")

    verdict = data.get("verdict", "parcial")
    if verdict not in {"correta", "parcial", "incorreta"}:
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
    if payload.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(status_code=422, detail="Dificuldade invalida.")

    card = crud.update_flashcard_difficulty(db, card_id, payload.difficulty, user_id=current_user.id)
    if not card:
        raise HTTPException(status_code=404, detail="Card nao encontrado.")

    return {"status": "ok", "difficulty": card.difficulty}


@router.delete("/flashcards/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deck = crud.get_flashcard_deck_by_user_and_id(db, current_user.id, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck nao encontrado.")
    crud.delete_flashcard_deck(db, deck)
