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
from docops.db.database import get_db, session_scope
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


def _run_digest_with_thread_session(
    doc_name: str,
    doc_id: str,
    user_id: int,
    generate_flashcards: bool,
    extract_tasks: bool,
    num_cards: int,
    max_tasks: int,
    db_bind,
    schedule_reviews: bool = False,
) -> dict:
    with session_scope(bind=db_bind) as db_local:
        return _run_digest(
            doc_name,
            doc_id,
            user_id,
            generate_flashcards,
            extract_tasks,
            num_cards,
            max_tasks,
            db_local,
            schedule_reviews,
        )


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

def _run_study_plan_with_thread_session(
    doc_name: str,
    doc_id: str,
    user_id: int,
    hours_per_day: float,
    deadline,
    db_bind,
    generate_flashcards: bool,
    num_cards: int,
    preferred_start_time: str,
) -> dict:
    from docops.services import study_plan_generator

    with session_scope(bind=db_bind) as db_local:
        return study_plan_generator.generate_study_plan(
            doc_name,
            doc_id,
            user_id,
            hours_per_day,
            deadline,
            db_local,
            generate_flashcards,
            num_cards,
            preferred_start_time,
        )


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
    db_bind = db.get_bind()

    result = await asyncio.to_thread(
        _run_digest_with_thread_session,
        doc_record.file_name,
        doc_record.doc_id,
        current_user.id,
        payload.generate_flashcards,
        payload.extract_tasks,
        payload.num_cards,
        payload.max_tasks,
        db_bind,
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

    db_bind = db.get_bind()
    result = await asyncio.to_thread(
        _run_study_plan_with_thread_session,
        doc_record.file_name,
        doc_record.doc_id,
        current_user.id,
        payload.hours_per_day,
        deadline,
        db_bind,
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


# ── Daily Question ─────────────────────────────────────────────────────────────

_DAILY_QUESTION_PROMPT = """\
Você é um professor que cria perguntas de revisão instigantes. Com base nos fragmentos do documento abaixo, crie UMA pergunta de reflexão ou compreensão que estimule o pensamento crítico do estudante.

Documento: {doc_name}
Fragmentos:
{content}

Retorne APENAS JSON (sem markdown, sem texto extra):
{{"question": "A pergunta aqui (1-2 frases diretas)", "answer_hint": "Dica ou resposta resumida (2-4 frases)"}}
"""


def _generate_daily_question_llm(doc_name: str, content: str) -> tuple[str, str]:
    from docops.config import config
    from google import genai

    client = genai.Client(api_key=config.gemini_api_key)
    model = getattr(config, "gemini_model_cheap", None) or config.gemini_model
    prompt = _DAILY_QUESTION_PROMPT.format(doc_name=doc_name, content=content[:6000])
    response = client.models.generate_content(model=model, contents=prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    return data["question"], data.get("answer_hint", "")


@router.get("/pipeline/daily-question")
async def get_daily_question(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna (ou gera) a pergunta do dia a partir dos documentos do usuário."""
    import random
    from datetime import date

    today = date.today().isoformat()

    # Verifica cache diário
    existing = crud.get_daily_question_for_user(db, current_user.id, today)
    if existing:
        return {
            "question": existing.question,
            "answer_hint": existing.answer_hint,
            "doc_name": existing.doc_name,
            "date": existing.date_generated,
        }

    docs = crud.list_documents_for_user(db, current_user.id)
    if not docs:
        return {"question": None, "answer_hint": None, "doc_name": None, "date": today}

    doc = random.choice(docs)

    def _gen() -> tuple[str, str] | tuple[None, None]:
        from docops.rag.retriever import retrieve_for_doc
        chunks = retrieve_for_doc(
            doc.file_name,
            query="conceito importante, definição, princípio fundamental",
            doc_id=doc.doc_id,
            user_id=current_user.id,
            top_k=10,
        )
        if not chunks:
            return None, None
        content = "\n\n".join(c.page_content[:400] for c in chunks[:8])
        return _generate_daily_question_llm(doc.file_name, content)

    try:
        question, answer_hint = await asyncio.to_thread(_gen)
    except Exception as exc:
        logger.warning("Falha ao gerar pergunta do dia: %s", exc)
        return {"question": None, "answer_hint": None, "doc_name": None, "date": today}

    if question:
        record = crud.create_daily_question(
            db,
            user_id=current_user.id,
            question=question,
            answer_hint=answer_hint or "",
            doc_name=doc.file_name,
            date_generated=today,
        )
        return {
            "question": record.question,
            "answer_hint": record.answer_hint,
            "doc_name": record.doc_name,
            "date": record.date_generated,
        }

    return {"question": None, "answer_hint": None, "doc_name": None, "date": today}


# ── Gap Analysis ───────────────────────────────────────────────────────────────

_GAP_ANALYSIS_PROMPT = """\
Você é um especialista em análise de aprendizado. Analise os dados abaixo e identifique lacunas de conhecimento — tópicos presentes nos documentos mas não cobertos pelos flashcards ou tarefas do usuário.

Documentos disponíveis:
{docs_section}

Flashcards criados (tópicos já estudados):
{cards_section}

Tarefas criadas:
{tasks_section}

Amostra do conteúdo dos documentos:
{content_section}

Retorne APENAS JSON array (sem markdown, sem texto extra). Máximo 8 gaps:
[
  {{
    "topico": "Nome específico do tópico lacunado",
    "descricao": "Por que este tópico é importante e está faltando",
    "prioridade": "high|normal|low",
    "sugestao": "Ação recomendada: criar flashcard, adicionar tarefa, estudar seção X, etc."
  }}
]

Prioridade 'high' = tópico fundamental não coberto. Seja específico e acionável.
"""


def _run_gap_analysis(user_id: int, doc_names: list[str], db: Session) -> list[dict]:
    from docops.config import config
    from docops.db.models import TaskRecord
    from docops.rag.retriever import retrieve_for_doc
    from google import genai

    docs = crud.list_documents_for_user(db, user_id)
    if not docs:
        return []

    target_docs = [d for d in docs if not doc_names or d.file_name in doc_names] or docs[:3]

    docs_section = "\n".join(f"- {d.file_name} ({d.chunk_count} chunks)" for d in target_docs[:5])

    decks = crud.list_flashcard_decks_for_user(db, user_id)
    card_fronts: list[str] = []
    for deck_item in decks[:3]:
        card_fronts.extend(c.front[:80] for c in deck_item.cards[:10])
    cards_section = "\n".join(f"- {f}" for f in card_fronts[:30]) or "(nenhum flashcard criado)"

    tasks = (
        db.query(TaskRecord)
        .filter_by(user_id=user_id)
        .order_by(TaskRecord.created_at.desc())
        .limit(20)
        .all()
    )
    tasks_section = "\n".join(f"- {t.title}" for t in tasks) or "(nenhuma tarefa criada)"

    content_parts: list[str] = []
    for doc in target_docs[:2]:
        chunks = retrieve_for_doc(
            doc.file_name,
            query="tópicos principais, conceitos, capítulos, seções",
            doc_id=doc.doc_id,
            user_id=user_id,
            top_k=12,
        )
        if chunks:
            content_parts.append(
                f"\n### {doc.file_name}\n" + "\n".join(c.page_content[:300] for c in chunks[:8])
            )
    content_section = "\n".join(content_parts)[:8000]

    prompt = _GAP_ANALYSIS_PROMPT.format(
        docs_section=docs_section,
        cards_section=cards_section,
        tasks_section=tasks_section,
        content_section=content_section,
    )

    client = genai.Client(api_key=config.gemini_api_key)
    model = getattr(config, "gemini_model_cheap", None) or config.gemini_model
    response = client.models.generate_content(model=model, contents=prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        gaps = json.loads(text)
        if not isinstance(gaps, list):
            return []
        valid = {"high", "normal", "low"}
        return [
            {
                "topico": str(g.get("topico", "")).strip(),
                "descricao": str(g.get("descricao", "")).strip(),
                "prioridade": g.get("prioridade", "normal") if g.get("prioridade") in valid else "normal",
                "sugestao": str(g.get("sugestao", "")).strip(),
            }
            for g in gaps if g.get("topico")
        ][:8]
    except Exception as exc:
        logger.warning("Falha ao parsear gaps: %s", exc)
        return []


def _run_gap_analysis_with_thread_session(
    user_id: int,
    doc_names: list[str],
    db_bind,
) -> list[dict]:
    with session_scope(bind=db_bind) as db_local:
        return _run_gap_analysis(user_id, doc_names, db_local)


class GapAnalysisRequest(BaseModel):
    doc_names: list[str] = Field(default_factory=list)  # vazio = todos os docs


class GapItem(BaseModel):
    topico: str
    descricao: str
    prioridade: str
    sugestao: str


class GapAnalysisResponse(BaseModel):
    gaps: list[GapItem]
    docs_analyzed: int


@router.post("/pipeline/gap-analysis", response_model=GapAnalysisResponse)
async def run_gap_analysis(
    payload: GapAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Analisa lacunas de aprendizado: tópicos nos docs não cobertos por flashcards/tarefas."""
    docs = crud.list_documents_for_user(db, current_user.id)
    if not docs:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado.")

    logger.info(
        "Gap analysis solicitada por user=%d, %d doc(s) alvo",
        current_user.id, len(payload.doc_names) or len(docs),
    )
    db_bind = db.get_bind()

    try:
        gaps_raw = await asyncio.to_thread(
            _run_gap_analysis_with_thread_session,
            current_user.id,
            payload.doc_names,
            db_bind,
        )
    except Exception as exc:
        logger.error("Falha na gap analysis: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro na análise: {exc}")

    target_count = len([d for d in docs if not payload.doc_names or d.file_name in payload.doc_names]) or len(docs)
    return GapAnalysisResponse(
        gaps=[GapItem(**g) for g in gaps_raw],
        docs_analyzed=min(target_count, 3),
    )


# ── Evaluate Answer ─────────────────────────────────────────────────────────────

_EVALUATE_ANSWER_PROMPT = """\
Você é um professor avaliando a resposta de um estudante de forma construtiva.

Pergunta: {question}
Dica/gabarito resumido: {answer_hint}
Resposta do estudante: {user_answer}

REGRAS IMPORTANTES:
1. Se a "resposta" for uma solicitação para você explicar (ex: "me diga a resposta", "qual é a resposta", "explique", "não sei"), \
retorne: {{"feedback": "Não identifiquei uma tentativa de resposta. Por favor, escreva o que você sabe sobre o tema, mesmo que seja pouco — \
a avaliação só funciona com uma resposta genuína.", "score": "sem_resposta"}}
2. Se a resposta for genuína mas incompleta ou incorreta, avalie normalmente.
3. Para respostas reais: avalie em 2-4 frases — o que está correto, incompleto, e o que pode ser aprofundado. Seja encorajador mas preciso.

Retorne APENAS JSON (sem markdown):
{{"feedback": "avaliação aqui", "score": "excelente|bom|parcial|incorreto|sem_resposta"}}
"""


class EvaluateAnswerRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    user_answer: str = Field(min_length=1, max_length=4000)
    answer_hint: str = Field(default="", max_length=2000)


class EvaluateAnswerResponse(BaseModel):
    feedback: str
    score: str  # excelente | bom | parcial | incorreto


def _run_evaluate_answer(question: str, user_answer: str, answer_hint: str) -> tuple[str, str]:
    from docops.config import config
    from google import genai

    client = genai.Client(api_key=config.gemini_api_key)
    model = getattr(config, "gemini_model_cheap", None) or config.gemini_model
    prompt = _EVALUATE_ANSWER_PROMPT.format(
        question=question,
        answer_hint=answer_hint or "não fornecida",
        user_answer=user_answer,
    )
    response = client.models.generate_content(model=model, contents=prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    return data["feedback"], data.get("score", "parcial")


@router.post("/pipeline/evaluate-answer", response_model=EvaluateAnswerResponse)
async def evaluate_answer(
    payload: EvaluateAnswerRequest,
    current_user: User = Depends(get_current_user),
):
    """Avalia a resposta do usuário a uma pergunta do dia."""
    try:
        feedback, score = await asyncio.to_thread(
            _run_evaluate_answer,
            payload.question,
            payload.user_answer,
            payload.answer_hint,
        )
    except Exception as exc:
        logger.error("Falha ao avaliar resposta: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro ao avaliar: {exc}")

    return EvaluateAnswerResponse(feedback=feedback, score=score)
