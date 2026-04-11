"""Flashcard routes exposed under /api/flashcards."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from typing import Literal, Optional

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
FLASHCARD_GENERATION_MAX_ATTEMPTS = 6
SEMANTIC_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "qual",
    "quais",
    "que",
    "se",
    "sem",
    "sobre",
    "um",
    "uma",
    "uns",
    "umas",
}
SEMANTIC_INTENT_TOKENS = {
    "conceito",
    "defina",
    "definicao",
    "descreva",
    "diferenca",
    "diferencas",
    "explique",
    "finalidade",
    "funcao",
    "importancia",
    "objetivo",
    "papel",
    "serve",
    "significa",
}


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


class BatchGenerateRequest(BaseModel):
    all_docs: bool = False
    doc_names: list[str] = Field(
        default_factory=list,
        description="Specific document file names to process. Ignored when all_docs=true.",
    )
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


class BatchGenerateItem(BaseModel):
    requested_doc_name: str
    source_doc: Optional[str] = None
    status: Literal["created", "failed"]
    deck: Optional[DeckResponse] = None
    error: Optional[str] = None


class BatchGenerateResponse(BaseModel):
    requested_docs: int
    created: int
    failed: int
    items: list[BatchGenerateItem]


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
Regras de qualidade:
- COBERTURA AMPLA: distribua as perguntas por DIFERENTES topicos e secoes do conteudo. Nao concentre multiplas perguntas no mesmo conceito ou paragrafo.
- VARIEDADE de tipos: misture definicoes, fatos numericos, relacoes causais, comparacoes, aplicacoes praticas e exemplos concretos.
- UNICIDADE absoluta: nenhuma pergunta pode ser semanticamente equivalente a outra, mesmo que use palavras diferentes. Antes de incluir uma pergunta, verifique se ela ja foi coberta sob outro angulo.
- Respostas devem ser curtas e diretas (1-3 frases).
- O campo "difficulty" deve ser: "facil" (fato direto/definicao simples), "media" (requer compreensao/conexao) ou "dificil" (requer analise/aplicacao avancada).
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


def _resolve_num_cards(num_cards: int, difficulty_mode: str, difficulty_custom: dict | None) -> int:
    if difficulty_mode == "custom" and difficulty_custom:
        resolved = sum(int(value) for value in difficulty_custom.values())
        if resolved < 1:
            raise HTTPException(status_code=422, detail="A distribuicao personalizada deve ter ao menos 1 card.")
        return resolved
    return num_cards


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


def _semantic_tokens(value: str) -> set[str]:
    normalized = _normalize_card_text(value)
    tokens: set[str] = set()
    for token in normalized.split():
        if token in SEMANTIC_STOPWORDS or token in SEMANTIC_INTENT_TOKENS:
            continue
        if len(token) <= 2 and not token.isdigit():
            continue
        tokens.add(token)
    return tokens


def _token_overlap_metrics(tokens_a: set[str], tokens_b: set[str]) -> tuple[float, float, int]:
    if not tokens_a or not tokens_b:
        return 0.0, 0.0, 0

    intersection = len(tokens_a & tokens_b)
    if intersection == 0:
        return 0.0, 0.0, 0

    union = len(tokens_a | tokens_b)
    jaccard = intersection / union
    coverage = intersection / min(len(tokens_a), len(tokens_b))
    return jaccard, coverage, intersection


def _is_semantic_text_duplicate(text_a: str, text_b: str) -> bool:
    normalized_a = _normalize_card_text(text_a)
    normalized_b = _normalize_card_text(text_b)
    if not normalized_a or not normalized_b:
        return False

    if normalized_a == normalized_b:
        return True

    if min(len(normalized_a), len(normalized_b)) >= 25 and (
        normalized_a in normalized_b or normalized_b in normalized_a
    ):
        return True

    tokens_a = _semantic_tokens(normalized_a)
    tokens_b = _semantic_tokens(normalized_b)
    if SequenceMatcher(None, normalized_a, normalized_b).ratio() >= 0.93 and tokens_a == tokens_b:
        return True
    if tokens_a and tokens_a == tokens_b and len(tokens_a) >= 2:
        return True

    jaccard, coverage, intersection = _token_overlap_metrics(tokens_a, tokens_b)
    if intersection >= 3 and jaccard >= 0.75:
        return True
    if intersection >= 4 and coverage >= 0.8:
        return True

    return False


def _is_semantic_card_duplicate(candidate: dict, existing: dict) -> bool:
    if _is_semantic_text_duplicate(candidate["front"], existing["front"]):
        return True

    candidate_front_tokens = _semantic_tokens(candidate["front"])
    existing_front_tokens = _semantic_tokens(existing["front"])
    front_jaccard, front_coverage, front_intersection = _token_overlap_metrics(
        candidate_front_tokens,
        existing_front_tokens,
    )
    if front_intersection < 2:
        return False

    candidate_back = _normalize_card_text(candidate["back"])
    existing_back = _normalize_card_text(existing["back"])
    back_ratio = SequenceMatcher(None, candidate_back, existing_back).ratio()
    back_jaccard, _, back_intersection = _token_overlap_metrics(
        _semantic_tokens(candidate["back"]),
        _semantic_tokens(existing["back"]),
    )

    if front_jaccard >= 0.6 and front_coverage >= 0.75 and back_ratio >= 0.75:
        return True
    if front_coverage >= 0.9 and back_intersection >= 2 and back_jaccard >= 0.5:
        return True

    return False


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


def _dedupe_cards(
    cards: list[object],
    *,
    seen_fronts: set[str] | None = None,
    existing_cards: list[dict] | None = None,
) -> list[dict]:
    accepted: list[dict] = []
    seen_front_keys = set(seen_fronts or set())
    seen_pairs: set[tuple[str, str]] = set()
    semantic_pool: list[dict] = list(existing_cards or [])

    for raw_card in cards:
        card = _sanitize_card(raw_card)
        if not card:
            continue

        front_key = _normalize_card_text(card["front"])
        back_key = _normalize_card_text(card["back"])
        pair_key = (front_key, back_key)

        if not front_key or front_key in seen_front_keys or pair_key in seen_pairs:
            continue
        if any(_is_semantic_card_duplicate(card, existing) for existing in semantic_pool):
            continue

        seen_front_keys.add(front_key)
        seen_pairs.add(pair_key)
        accepted.append(card)
        semantic_pool.append(card)

    return accepted


def _partition_persisted_cards_by_uniqueness(cards: list[object]) -> tuple[list[object], list[object]]:
    ordered_cards = sorted(cards, key=lambda item: int(getattr(item, "id", 0) or 0))
    accepted_cards: list[object] = []
    duplicate_cards: list[object] = []
    accepted_payloads: list[dict] = []
    seen_fronts: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()

    for persisted_card in ordered_cards:
        payload = _sanitize_card(
            {
                "front": str(getattr(persisted_card, "front", "")),
                "back": str(getattr(persisted_card, "back", "")),
                "difficulty": str(getattr(persisted_card, "difficulty", "media")),
            }
        )
        if not payload:
            duplicate_cards.append(persisted_card)
            continue

        front_key = _normalize_card_text(payload["front"])
        back_key = _normalize_card_text(payload["back"])
        pair_key = (front_key, back_key)

        if not front_key or front_key in seen_fronts or pair_key in seen_pairs:
            duplicate_cards.append(persisted_card)
            continue

        if any(_is_semantic_card_duplicate(payload, existing) for existing in accepted_payloads):
            duplicate_cards.append(persisted_card)
            continue

        accepted_cards.append(persisted_card)
        accepted_payloads.append(payload)
        seen_fronts.add(front_key)
        seen_pairs.add(pair_key)

    return accepted_cards, duplicate_cards


def _repair_deck_uniqueness(db: Session, deck) -> int:
    if not getattr(deck, "cards", None):
        return 0

    _accepted, duplicates = _partition_persisted_cards_by_uniqueness(list(deck.cards))
    if not duplicates:
        return 0

    for card in duplicates:
        db.delete(card)
    db.commit()
    db.refresh(deck)
    logger.warning(
        "Deck %s reparado automaticamente: %d card(s) duplicado(s) removido(s).",
        getattr(deck, "id", "unknown"),
        len(duplicates),
    )
    return len(duplicates)


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
        return (
            "\nUnicidade: todas as perguntas devem ser semanticamente diferentes entre si. "
            "Nao repita o mesmo conceito com palavras diferentes. "
            "Cada pergunta deve explorar um aspecto distinto do conteudo.\n"
        )

    sample = "\n".join(f"- {front}" for front in excluded_fronts[:30])
    return (
        "\nUnicidade OBRIGATORIA: as perguntas abaixo ja foram geradas. "
        "Voce NAO pode repetir nem parafrasear nenhuma delas, nem abordar o mesmo conceito por outro angulo. "
        "Explore partes do conteudo ainda nao cobertas.\n"
        "Perguntas ja existentes (proibidas):\n"
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
        content=content[:24000],
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

        prepared_cards = _dedupe_cards(
            batch,
            seen_fronts=seen_fronts,
            existing_cards=accepted,
        )
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


def _collect_diverse_chunks(
    doc_name: str,
    doc_id: str,
    user_id: int,
    content_filter: str,
) -> list:
    """Retrieve a broad, topic-diverse set of chunks from the document.

    Instead of a single RAG query (which returns thematically clustered chunks),
    we fan out across several different query angles so the final content pool
    covers as many distinct topics in the document as possible.
    """
    from docops.rag.retriever import retrieve_for_doc

    if content_filter.strip():
        # Focused mode: user explicitly requested a specific topic
        chunks = retrieve_for_doc(doc_name, query=content_filter.strip(), doc_id=doc_id, user_id=user_id, top_k=50)
        return chunks[:40]

    # Broad mode: use multiple complementary queries to maximise topical coverage
    diverse_queries = [
        "conceitos principais e definicoes",
        "processos metodologias e tecnicas",
        "exemplos casos praticos e aplicacoes",
        "comparacoes diferencas e relacoes entre conceitos",
        "consequencias resultados e conclusoes",
        "formula equacao calculo e metrica",
        "historico origem contexto e evolucao",
        "vantagens desvantagens limitacoes e criticas",
    ]

    seen_ids: set[str] = set()
    merged: list = []

    per_query_k = 15
    for query in diverse_queries:
        batch = retrieve_for_doc(doc_name, query=query, doc_id=doc_id, user_id=user_id, top_k=per_query_k)
        for chunk in batch:
            # Deduplicate by chunk content hash to avoid the same chunk appearing twice
            chunk_key = chunk.page_content[:120]
            if chunk_key not in seen_ids:
                seen_ids.add(chunk_key)
                merged.append(chunk)

    return merged


def _generate_cards(
    doc_name: str,
    doc_id: str,
    user_id: int,
    num_cards: int,
    content_filter: str = "",
    difficulty_mode: str = "any",
    difficulty_custom: dict | None = None,
) -> list[dict]:
    from docops.services.flashcard_generation import generate_cards

    return generate_cards(
        doc_name=doc_name,
        doc_id=doc_id,
        user_id=user_id,
        num_cards=num_cards,
        content_filter=content_filter,
        difficulty_mode=difficulty_mode,
        difficulty_custom=difficulty_custom,
    )


async def _generate_deck_for_document(
    *,
    db: Session,
    user_id: int,
    doc_record,
    num_cards: int,
    content_filter: str,
    difficulty_mode: str,
    difficulty_custom: dict | None,
):
    cards = await asyncio.to_thread(
        _generate_cards,
        doc_record.file_name,
        doc_record.doc_id,
        user_id,
        num_cards,
        content_filter,
        difficulty_mode,
        difficulty_custom,
    )

    return crud.create_flashcard_deck(
        db,
        user_id=user_id,
        title=f"Flashcards - {doc_record.file_name}",
        source_doc=doc_record.file_name,
        cards=cards,
    )


def _resolve_batch_documents(
    db: Session,
    user_id: int,
    *,
    all_docs: bool,
    doc_names: list[str],
):
    documents = crud.list_documents_for_user(db, user_id)
    if all_docs and doc_names:
        raise HTTPException(status_code=422, detail="Use all_docs=true ou doc_names, nao ambos.")

    if all_docs:
        return [(doc.file_name, doc) for doc in documents]

    cleaned_names = [name.strip() for name in doc_names if name and name.strip()]
    if not cleaned_names:
        raise HTTPException(status_code=422, detail="Informe all_docs=true ou pelo menos um doc_name.")

    lookup = {_normalize_card_text(doc.file_name): doc for doc in documents}
    selected: list[tuple[str, object | None]] = []
    seen: set[str] = set()

    for requested_name in cleaned_names:
        key = _normalize_card_text(requested_name)
        if key in seen:
            continue
        seen.add(key)
        selected.append((requested_name, lookup.get(key)))

    return selected


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


@router.post("/flashcards/generate-batch", response_model=BatchGenerateResponse)
async def generate_decks_batch(
    payload: BatchGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    num_cards = _resolve_num_cards(payload.num_cards, payload.difficulty_mode, payload.difficulty_custom)
    targets = _resolve_batch_documents(
        db,
        current_user.id,
        all_docs=payload.all_docs,
        doc_names=payload.doc_names,
    )

    items: list[BatchGenerateItem] = []
    created = 0
    failed = 0

    for requested_doc_name, doc_record in targets:
        if doc_record is None:
            failed += 1
            items.append(
                BatchGenerateItem(
                    requested_doc_name=requested_doc_name,
                    source_doc=None,
                    status="failed",
                    error="Documento nao encontrado ou nao pertence ao usuario.",
                )
            )
            continue

        try:
            deck = await _generate_deck_for_document(
                db=db,
                user_id=current_user.id,
                doc_record=doc_record,
                num_cards=num_cards,
                content_filter=payload.content_filter,
                difficulty_mode=payload.difficulty_mode,
                difficulty_custom=payload.difficulty_custom,
            )
            created += 1
            items.append(
                BatchGenerateItem(
                    requested_doc_name=requested_doc_name,
                    source_doc=doc_record.file_name,
                    status="created",
                    deck=DeckResponse.model_validate(deck),
                )
            )
        except HTTPException as exc:
            failed += 1
            items.append(
                BatchGenerateItem(
                    requested_doc_name=requested_doc_name,
                    source_doc=doc_record.file_name,
                    status="failed",
                    error=str(exc.detail),
                )
            )
        except Exception as exc:
            logger.exception("Falha ao gerar flashcards em lote para %s", doc_record.file_name)
            failed += 1
            items.append(
                BatchGenerateItem(
                    requested_doc_name=requested_doc_name,
                    source_doc=doc_record.file_name,
                    status="failed",
                    error="Erro inesperado ao gerar flashcards para este documento.",
                )
            )

    return BatchGenerateResponse(
        requested_docs=len(targets),
        created=created,
        failed=failed,
        items=items,
    )


@router.get("/flashcards/{deck_id}", response_model=DeckResponse)
def get_deck(
    deck_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deck = crud.get_flashcard_deck_by_user_and_id(db, current_user.id, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck nao encontrado.")
    _repair_deck_uniqueness(db, deck)
    return deck


@router.post("/flashcards/generate", response_model=DeckResponse)
async def generate_deck(
    payload: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from docops.services.ownership import require_user_document

    doc_record = require_user_document(db, current_user.id, payload.doc_name)

    num_cards = _resolve_num_cards(payload.num_cards, payload.difficulty_mode, payload.difficulty_custom)
    deck = await _generate_deck_for_document(
        db=db,
        user_id=current_user.id,
        doc_record=doc_record,
        num_cards=num_cards,
        content_filter=payload.content_filter,
        difficulty_mode=payload.difficulty_mode,
        difficulty_custom=payload.difficulty_custom,
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
