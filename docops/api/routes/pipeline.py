"""Cross-module pipeline routes — /api/pipeline.

Smart Digest: gera resumo + flashcards + extrai tarefas de um documento em uma operação.
Extract Tasks: extrai itens acionáveis de um documento e os cria na lista de tarefas.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.services.ownership import require_user_document

logger = get_logger("docops.api.pipeline")
router = APIRouter()


# ── Prompt de extração de tarefas ────────────────────────────────────────────

_TASK_EXTRACT_PROMPT = """\
Você é um extrator de tarefas e itens acionáveis. Analise o conteúdo abaixo e extraia APENAS itens que representam ações concretas (tarefas, exercícios, entregas, revisões, leituras).

Ignore conceitos teóricos, definições e contexto expositivo puro.

Retorne APENAS um JSON array. Sem markdown, sem texto extra.
Formato: [{{"title": "Verbo + ação curta (máx 100 chars)", "note": "Contexto útil ou null", "priority": "low|normal|high"}}]

Regras:
- No máximo {max_tasks} itens
- "high": prazo urgente, avaliação, entrega
- "normal": leitura, estudo, revisão de conteúdo
- "low": exercício opcional, material extra
- Título começa com verbo (Estudar, Revisar, Resolver, Entregar, Ler, Implementar, etc.)

Conteúdo:
{content}"""


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _extract_task_items(content: str, max_tasks: int) -> list[dict]:
    """Usa LLM para extrair tarefas acionáveis de um bloco de texto."""
    from docops.config import config
    from google import genai

    client = genai.Client(api_key=config.gemini_api_key)
    prompt = _TASK_EXTRACT_PROMPT.format(content=content[:12000], max_tasks=max_tasks)
    response = client.models.generate_content(model=config.gemini_model, contents=prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Falha ao parsear tarefas extraídas: %s", text[:300])
        return []

    if not isinstance(items, list):
        return []

    valid_priorities = {"low", "normal", "high"}
    result = []
    for i in items:
        title = str(i.get("title", "")).strip()[:512]
        if not title:
            continue
        result.append({
            "title": title,
            "note": str(i["note"]).strip() if i.get("note") else None,
            "priority": i.get("priority", "normal") if i.get("priority") in valid_priorities else "normal",
        })
    return result[:max_tasks]


def _schedule_srs_reminders(deck_id: int, deck_title: str, user_id: int, db: Session) -> int:
    """Cria lembretes de revisão espaçada (SRS) para um deck de flashcards.

    Agenda: +1 dia, +3 dias, +7 dias a partir de hoje às 19h.
    Retorna o número de lembretes criados.
    """
    from datetime import datetime, timedelta, timezone
    from docops.db import crud as _crud

    now = datetime.now(timezone.utc)
    slots = [
        ("🔁 1ª revisão", now + timedelta(days=1)),
        ("🔁 2ª revisão", now + timedelta(days=3)),
        ("🔁 3ª revisão", now + timedelta(days=7)),
    ]
    created = 0
    for label, dt in slots:
        scheduled = dt.replace(hour=19, minute=0, second=0, microsecond=0)
        try:
            _crud.create_reminder_record(
                db,
                user_id=user_id,
                title=f"{label} — {deck_title}",
                starts_at=scheduled,
                note=f"Revisão espaçada automática. Deck ID: {deck_id}",
            )
            created += 1
        except Exception as exc:
            logger.warning("Falha ao criar lembrete SRS para deck %d: %s", deck_id, exc)
    return created


def _run_digest(
    doc_name: str,
    doc_id: str,
    user_id: int,
    generate_flashcards: bool,
    extract_tasks: bool,
    num_cards: int,
    max_tasks: int,
    db: Session,
    schedule_reviews: bool = False,
) -> dict:
    from docops.graph.graph import run as graph_run
    from docops.rag.retriever import retrieve_for_doc

    # 1. Recupera chunks do documento
    chunks = retrieve_for_doc(
        doc_name,
        query="conteúdo principal do documento",
        doc_id=doc_id,
        user_id=user_id,
        top_k=60,
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="Nenhum chunk encontrado para este documento.")

    content = "\n\n".join(c.page_content[:800] for c in chunks[:30])

    # 2. Gera resumo breve via grafo LangGraph
    state = graph_run(
        query=f"Faça um resumo analítico do documento '{doc_name}'.",
        user_id=user_id,
        extra={"doc_name": doc_name, "doc_id": doc_id, "summary_mode": "brief"},
    )
    summary = state.get("answer", "")

    # 3. Gera flashcards
    deck_id: Optional[int] = None
    if generate_flashcards:
        try:
            from docops.api.routes.flashcards import _generate_cards
            cards = _generate_cards(
                doc_name=doc_name,
                doc_id=doc_id,
                user_id=user_id,
                num_cards=num_cards,
            )
            deck = crud.create_flashcard_deck(
                db,
                user_id=user_id,
                title=f"Flashcards — {doc_name}",
                source_doc=doc_name,
                cards=cards,
            )
            deck_id = deck.id
            logger.info("Smart Digest: deck criado (id=%s, %d cards)", deck_id, len(cards))
            if schedule_reviews:
                n = _schedule_srs_reminders(deck_id, deck.title, user_id, db)
                logger.info("Smart Digest: %d lembretes SRS agendados para deck %d", n, deck_id)
        except Exception as exc:
            logger.warning("Falha ao gerar flashcards no digest: %s", exc)

    # 4. Extrai e cria tarefas
    tasks_created = 0
    task_titles: list[str] = []
    if extract_tasks:
        try:
            task_items = _extract_task_items(content, max_tasks)
            for item in task_items:
                crud.create_task_record(
                    db,
                    user_id=user_id,
                    title=item["title"],
                    note=item.get("note"),
                    priority=item.get("priority", "normal"),
                )
                task_titles.append(item["title"])
            tasks_created = len(task_titles)
            logger.info("Smart Digest: %d tarefas criadas", tasks_created)
        except Exception as exc:
            logger.warning("Falha ao extrair tarefas no digest: %s", exc)

    return {
        "summary": summary,
        "deck_id": deck_id,
        "tasks_created": tasks_created,
        "task_titles": task_titles,
        "reviews_scheduled": 3 if (deck_id and schedule_reviews) else 0,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

class DigestRequest(BaseModel):
    doc_name: str = Field(min_length=1)
    generate_flashcards: bool = True
    extract_tasks: bool = True
    num_cards: int = Field(default=10, ge=1, le=30)
    max_tasks: int = Field(default=8, ge=1, le=20)
    schedule_reviews: bool = False  # Agenda revisões SRS no calendário ao criar deck


class DigestResponse(BaseModel):
    summary: str
    deck_id: Optional[int]
    tasks_created: int
    task_titles: list[str]
    reviews_scheduled: int = 0  # Número de lembretes SRS criados


class ExtractTasksRequest(BaseModel):
    doc_name: str = Field(min_length=1)
    max_tasks: int = Field(default=10, ge=1, le=20)


class ExtractTasksResponse(BaseModel):
    tasks_created: int
    titles: list[str]


class StudyPlanRequest(BaseModel):
    doc_name: str = Field(min_length=1)
    hours_per_day: float = Field(default=2.0, ge=0.5, le=12.0)
    deadline_date: str  # ISO YYYY-MM-DD
    generate_flashcards: bool = True
    num_cards: int = Field(default=15, ge=5, le=30)
    preferred_start_time: str = Field(default="20:00")  # HH:MM — horário preferido para as sessões


class StudyPlanConflict(BaseModel):
    date: str
    session_time: str
    conflicting_with: str
    conflicting_time: str


class StudyPlanResponse(BaseModel):
    plan_text: str
    tasks_created: int
    reminders_created: int
    sessions_count: int
    deck_id: Optional[int]
    titulo: str
    study_plan_id: Optional[int] = None
    conflicts: list[StudyPlanConflict] = []


class StudyPlanListItem(BaseModel):
    id: int
    titulo: str
    doc_name: str
    tasks_created: int
    reminders_created: int
    sessions_count: int
    deck_id: Optional[int]
    hours_per_day: float
    deadline_date: str
    created_at: str
    plan_text: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/pipeline/digest", response_model=DigestResponse)
async def digest_document(
    payload: DigestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smart Digest: gera resumo + flashcards + extrai tarefas em uma única operação."""
    doc_record = require_user_document(db, current_user.id, payload.doc_name)
    logger.info(
        "Smart Digest solicitado por user=%d para doc='%s'",
        current_user.id, payload.doc_name,
    )

    result = await asyncio.to_thread(
        _run_digest,
        doc_record.file_name,
        doc_record.doc_id,
        current_user.id,
        payload.generate_flashcards,
        payload.extract_tasks,
        payload.num_cards,
        payload.max_tasks,
        db,
        payload.schedule_reviews,
    )
    return DigestResponse(**result)


@router.post("/pipeline/extract-tasks", response_model=ExtractTasksResponse)
async def extract_tasks_from_doc(
    payload: ExtractTasksRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Extrai tarefas acionáveis de um documento e as adiciona à lista de tarefas."""
    from docops.rag.retriever import retrieve_for_doc

    doc_record = require_user_document(db, current_user.id, payload.doc_name)

    def _run() -> list[dict]:
        chunks = retrieve_for_doc(
            doc_record.file_name,
            query="tarefas, ações, exercícios, entregas, leituras",
            doc_id=doc_record.doc_id,
            user_id=current_user.id,
            top_k=30,
        )
        if not chunks:
            return []
        content = "\n\n".join(c.page_content[:800] for c in chunks[:20])
        return _extract_task_items(content, payload.max_tasks)

    task_items = await asyncio.to_thread(_run)

    titles: list[str] = []
    for item in task_items:
        crud.create_task_record(
            db,
            user_id=current_user.id,
            title=item["title"],
            note=item.get("note"),
            priority=item.get("priority", "normal"),
        )
        titles.append(item["title"])

    logger.info(
        "Extract tasks: %d tarefas criadas para user=%d, doc='%s'",
        len(titles), current_user.id, payload.doc_name,
    )
    return ExtractTasksResponse(tasks_created=len(titles), titles=titles)


@router.post("/pipeline/study-plan", response_model=StudyPlanResponse)
async def create_study_plan(
    payload: StudyPlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gera um plano de estudos completo: tópicos + sessões no calendário + tarefas + flashcards."""
    from datetime import date as _date

    doc_record = require_user_document(db, current_user.id, payload.doc_name)

    try:
        deadline = _date.fromisoformat(payload.deadline_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="deadline_date deve ser YYYY-MM-DD")

    if deadline <= _date.today():
        raise HTTPException(status_code=422, detail="deadline_date deve ser uma data futura")

    logger.info(
        "Study plan solicitado por user=%d para doc='%s', %gh/dia, prazo=%s, horário=%s",
        current_user.id, payload.doc_name, payload.hours_per_day, payload.deadline_date,
        payload.preferred_start_time,
    )

    from docops.services import study_plan_generator

    result = await asyncio.to_thread(
        study_plan_generator.generate_study_plan,
        doc_record.file_name,
        doc_record.doc_id,
        current_user.id,
        payload.hours_per_day,
        deadline,
        db,
        payload.generate_flashcards,
        payload.num_cards,
        payload.preferred_start_time,
    )

    # Salva o plano no banco de dados
    plan_record = crud.create_study_plan_record(
        db,
        user_id=current_user.id,
        titulo=result["titulo"],
        doc_name=doc_record.file_name,
        plan_text=result["plan_text"],
        tasks_created=result["tasks_created"],
        reminders_created=result["reminders_created"],
        sessions_count=result["sessions_count"],
        deck_id=result["deck_id"],
        hours_per_day=payload.hours_per_day,
        deadline_date=payload.deadline_date,
    )
    result["study_plan_id"] = plan_record.id
    logger.info("Study plan salvo (id=%d)", plan_record.id)

    return StudyPlanResponse(**result)


@router.get("/pipeline/study-plans", response_model=list[StudyPlanListItem])
async def list_study_plans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista planos de estudos salvos do usuário."""
    plans = crud.list_study_plans_for_user(db, current_user.id)
    return [
        StudyPlanListItem(
            id=p.id,
            titulo=p.titulo,
            doc_name=p.doc_name,
            tasks_created=p.tasks_created,
            reminders_created=p.reminders_created,
            sessions_count=p.sessions_count,
            deck_id=p.deck_id,
            hours_per_day=p.hours_per_day,
            deadline_date=p.deadline_date,
            created_at=p.created_at.isoformat(),
            plan_text=p.plan_text,
        )
        for p in plans
    ]


@router.delete("/pipeline/study-plans/{plan_id}")
async def delete_study_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove um plano de estudos salvo."""
    plan = crud.get_study_plan_by_user_and_id(db, current_user.id, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    crud.delete_study_plan_record(db, plan)
    return {"status": "deleted"}
