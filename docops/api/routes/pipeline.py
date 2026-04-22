"""Cross-module pipeline routes — /api/pipeline.

Smart Digest: gera resumo + flashcards + extrai tarefas de um documento em uma operação.
Extract Tasks: extrai itens acionáveis de um documento e os cria na lista de tarefas.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db, session_scope
from docops.db.models import User
from docops.features.entitlements import require_feature_and_capability
from docops.logging import get_logger
from docops.observability import emit_event
from docops.services.ownership import require_user_document

logger = get_logger("docops.api.pipeline")
router = APIRouter()

_RECOMMENDATION_CATEGORY_VALUES = {"coverage", "schedule", "quality", "consistency"}
_RECOMMENDATION_ACTION_VALUES = {
    "dismiss",
    "snooze",
    "mute_category",
    "feedback_useful",
    "feedback_not_useful",
}
_RECOMMENDATION_HISTORY_LOOKBACK_DAYS = 180
_RECOMMENDATION_DEDUP_WINDOW_HOURS = 8
_RECOMMENDATION_NOT_USEFUL_WINDOW_HOURS = 72


def _require_proactive_copilot_access(current_user: User) -> None:
    require_feature_and_capability(
        "proactive_copilot_enabled",
        "premium_proactive_copilot",
        current_user,
        feature_disabled_detail="Proactive copilot is disabled by feature flag.",
        capability_message="Proactive copilot is available only for premium users.",
    )


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


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
    """Create spaced repetition reminders (+1d, +3d, +7d at 19:00)."""
    from docops.services.flashcard_generation import schedule_srs_reminders

    return schedule_srs_reminders(deck_id=deck_id, deck_title=deck_title, user_id=user_id, db=db)


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
            from docops.services.flashcard_generation import generate_cards
            cards = generate_cards(
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


RecommendationCategory = Literal["coverage", "schedule", "quality", "consistency"]
RecommendationAction = Literal[
    "dismiss",
    "snooze",
    "mute_category",
    "feedback_useful",
    "feedback_not_useful",
]


class ProactiveRecommendationItem(BaseModel):
    id: str
    category: RecommendationCategory
    title: str
    description: str
    why_this: str
    action_label: str
    action_to: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    signals: dict[str, Any] = Field(default_factory=dict)


class ProactiveRecommendationsResponse(BaseModel):
    generated_at: str
    recommendation_count: int
    recommendations: list[ProactiveRecommendationItem]


class ProactiveRecommendationActionRequest(BaseModel):
    recommendation_id: str = Field(min_length=2, max_length=128)
    category: RecommendationCategory | None = None
    action: RecommendationAction
    duration_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    feedback_note: str | None = Field(default=None, max_length=512)


class ProactiveRecommendationActionResponse(BaseModel):
    status: str = "recorded"
    action: RecommendationAction
    event_type: str
    recommendation_id: str
    category: RecommendationCategory | None = None
    effective_until: str | None = None


def _parse_event_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _load_recommendation_controls(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime,
) -> dict[str, Any]:
    dedup_window_start = now_utc - timedelta(hours=_RECOMMENDATION_DEDUP_WINDOW_HOURS)
    history = crud.list_premium_analytics_events_for_user_since(
        db,
        user_id=user_id,
        since=now_utc - timedelta(days=_RECOMMENDATION_HISTORY_LOOKBACK_DAYS),
    )
    dismissed_ids: set[str] = set()
    snoozed_until: dict[str, datetime] = {}
    muted_category_until: dict[str, datetime] = {}
    recently_presented_ids: set[str] = set()
    category_not_useful_until: dict[str, datetime] = {}
    category_not_useful_count: dict[str, int] = {}

    for row in history:
        event_type = str(row.event_type or "").strip().lower()
        if not event_type.startswith("recommendation."):
            continue
        metadata = _parse_event_metadata(row.metadata_json)
        recommendation_id = str(metadata.get("recommendation_id") or "").strip().lower()
        category = str(metadata.get("category") or "").strip().lower()
        effective_until = _parse_iso_datetime(metadata.get("effective_until"))
        event_time = _to_utc_datetime(getattr(row, "created_at", None))

        if event_type == "recommendation.dismissed":
            if recommendation_id:
                dismissed_ids.add(recommendation_id)
            continue
        if event_type == "recommendation.snoozed":
            if recommendation_id and effective_until:
                previous = snoozed_until.get(recommendation_id)
                if previous is None or effective_until > previous:
                    snoozed_until[recommendation_id] = effective_until
            continue
        if event_type == "recommendation.category_muted":
            if category and effective_until:
                previous = muted_category_until.get(category)
                if previous is None or effective_until > previous:
                    muted_category_until[category] = effective_until
            continue
        if event_type in {"recommendation.presented", "recommendation.feed.generated"}:
            if event_time >= dedup_window_start:
                ids_raw = metadata.get("recommendation_ids")
                if isinstance(ids_raw, list):
                    for item in ids_raw:
                        recommendation_id_item = str(item or "").strip().lower()
                        if recommendation_id_item:
                            recently_presented_ids.add(recommendation_id_item)
                if recommendation_id:
                    recently_presented_ids.add(recommendation_id)
            continue
        if event_type == "recommendation.feedback.recorded":
            metadata_action = str(metadata.get("action") or "").strip().lower()
            useful = metadata.get("useful")
            is_not_useful = metadata_action == "feedback_not_useful" or useful is False
            if not is_not_useful or not category:
                continue
            category_not_useful_count[category] = int(category_not_useful_count.get(category, 0)) + 1
            penalty_until = event_time + timedelta(hours=_RECOMMENDATION_NOT_USEFUL_WINDOW_HOURS)
            previous = category_not_useful_until.get(category)
            if previous is None or penalty_until > previous:
                category_not_useful_until[category] = penalty_until

    return {
        "dismissed_ids": dismissed_ids,
        "snoozed_until": snoozed_until,
        "muted_category_until": muted_category_until,
        "recently_presented_ids": recently_presented_ids,
        "category_not_useful_until": category_not_useful_until,
        "category_not_useful_count": category_not_useful_count,
    }


def _build_proactive_recommendation_candidates(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    from docops.db.models import (
        ArtifactRecord,
        DailyQuestionRecord,
        FlashcardDeck,
        ReadingStatusRecord,
        ReminderRecord,
        ScheduleRecord,
        TaskRecord,
    )

    docs = crud.list_documents_for_user(db, user_id)
    doc_count = len(docs)
    artifact_count = int(db.query(ArtifactRecord).filter(ArtifactRecord.user_id == user_id).count() or 0)
    flashcard_deck_count = int(db.query(FlashcardDeck).filter(FlashcardDeck.user_id == user_id).count() or 0)

    overdue_count = int(
        db.query(TaskRecord)
        .filter(
            TaskRecord.user_id == user_id,
            TaskRecord.status != "done",
            TaskRecord.due_date.is_not(None),
            TaskRecord.due_date < now_utc,
        )
        .count()
        or 0
    )

    reading_in_progress = int(
        db.query(ReadingStatusRecord)
        .filter(
            ReadingStatusRecord.user_id == user_id,
            ReadingStatusRecord.status == "reading",
        )
        .count()
        or 0
    )

    day_start = datetime(
        year=now_utc.year,
        month=now_utc.month,
        day=now_utc.day,
        tzinfo=timezone.utc,
    )
    day_end = day_start + timedelta(days=1)
    reminders_today = int(
        db.query(ReminderRecord)
        .filter(
            ReminderRecord.user_id == user_id,
            ReminderRecord.starts_at >= day_start,
            ReminderRecord.starts_at < day_end,
        )
        .count()
        or 0
    )
    schedule_today = int(
        db.query(ScheduleRecord)
        .filter(
            ScheduleRecord.user_id == user_id,
            ScheduleRecord.active.is_(True),
            ScheduleRecord.day_of_week == now_utc.weekday(),
        )
        .count()
        or 0
    )

    today_key = day_start.date().isoformat()
    has_daily_question = bool(
        db.query(DailyQuestionRecord)
        .filter(
            DailyQuestionRecord.user_id == user_id,
            DailyQuestionRecord.date_generated == today_key,
        )
        .first()
    )

    deep_dossier_count = int(
        db.query(ArtifactRecord)
        .filter(
            ArtifactRecord.user_id == user_id,
            ArtifactRecord.template_id == "deep_dossier",
        )
        .count()
        or 0
    )

    candidates: list[dict[str, Any]] = []

    if overdue_count > 0:
        candidates.append(
            {
                "id": "overdue-tasks",
                "category": "consistency",
                "title": (
                    "Resolva 1 pendencia atrasada"
                    if overdue_count == 1
                    else f"Resolva {overdue_count} pendencias atrasadas"
                ),
                "description": "Limpar atrasos primeiro reduz friccao e melhora o ritmo da semana.",
                "why_this": (
                    "Foi detectada uma tarefa vencida."
                    if overdue_count == 1
                    else f"Foram detectadas {overdue_count} tarefas vencidas."
                ),
                "action_label": "Abrir tarefas",
                "action_to": "/tasks",
                "score": min(0.98, 0.9 + min(overdue_count, 8) * 0.01),
                "signals": {
                    "overdue_tasks": overdue_count,
                    "docs_count": doc_count,
                },
            }
        )

    if reading_in_progress > 0:
        candidates.append(
            {
                "id": "continue-where-stopped",
                "category": "consistency",
                "title": "Continue de onde voce parou",
                "description": "Retomar o material em progresso evita perda de contexto de estudo.",
                "why_this": (
                    "Existe 1 documento com leitura em andamento."
                    if reading_in_progress == 1
                    else f"Existem {reading_in_progress} documentos com leitura em andamento."
                ),
                "action_label": "Abrir documentos",
                "action_to": "/docs",
                "score": min(0.92, 0.82 + min(reading_in_progress, 5) * 0.02),
                "signals": {
                    "reading_in_progress": reading_in_progress,
                },
            }
        )

    if reminders_today > 0 or schedule_today > 0:
        candidates.append(
            {
                "id": "today-agenda",
                "category": "schedule",
                "title": "Revise sua agenda de hoje",
                "description": "Conferir compromissos do dia ajuda a proteger seu tempo de foco.",
                "why_this": (
                    f"Ha {reminders_today} lembrete(s) e {schedule_today} bloco(s) de agenda hoje."
                ),
                "action_label": "Ir para calendario",
                "action_to": "/schedule",
                "score": 0.74,
                "signals": {
                    "reminders_today": reminders_today,
                    "schedule_today": schedule_today,
                },
            }
        )

    if doc_count > 0 and artifact_count == 0:
        candidates.append(
            {
                "id": "first-artifact",
                "category": "coverage",
                "title": "Gere seu primeiro artefato consolidado",
                "description": "Transformar estudos em artefato acelera revisao e reaproveitamento.",
                "why_this": "Voce ja tem documentos indexados, mas ainda nao salvou artefatos.",
                "action_label": "Abrir artefatos",
                "action_to": "/artifacts",
                "score": 0.8,
                "signals": {
                    "docs_count": doc_count,
                    "artifacts_count": artifact_count,
                },
            }
        )

    if doc_count > 0 and flashcard_deck_count == 0:
        candidates.append(
            {
                "id": "weak-topics-review",
                "category": "coverage",
                "title": "Consolide topicos criticos em flashcards",
                "description": "Converter pontos-chave em cards melhora retencao e revisao ativa.",
                "why_this": "Seu workspace tem documentos, mas ainda sem decks de flashcards.",
                "action_label": "Criar flashcards",
                "action_to": "/flashcards",
                "score": 0.73,
                "signals": {
                    "docs_count": doc_count,
                    "flashcard_decks": flashcard_deck_count,
                },
            }
        )

    if doc_count > 0:
        candidates.append(
            {
                "id": "coverage-gap-analysis",
                "category": "coverage",
                "title": "Rode o mapa de lacunas",
                "description": "Identifique rapidamente onde faltam tarefas e flashcards.",
                "why_this": "Com documentos indexados, ja e possivel extrair lacunas de cobertura.",
                "action_label": "Abrir mapa de lacunas",
                "action_to": "/dashboard#gap-analysis-panel",
                "score": 0.69,
                "signals": {
                    "docs_count": doc_count,
                },
            }
        )

    if has_daily_question:
        candidates.append(
            {
                "id": "daily-question",
                "category": "quality",
                "title": "Responda a pergunta do dia",
                "description": "Uma resposta curta agora reforca aprendizado ativo sem interromper o fluxo.",
                "why_this": "Uma pergunta contextual foi gerada hoje para seus materiais.",
                "action_label": "Responder no dashboard",
                "action_to": "/dashboard",
                "score": 0.78,
                "signals": {
                    "daily_question_available": 1,
                },
            }
        )

    if doc_count > 0 and deep_dossier_count == 0:
        candidates.append(
            {
                "id": "recommended-deep-summary",
                "category": "quality",
                "title": "Crie um resumo profundo recomendado",
                "description": "Use um dossie detalhado para consolidar temas mais densos.",
                "why_this": "Ainda nao ha artefatos em template deep_dossier no seu historico.",
                "action_label": "Gerar resumo profundo",
                "action_to": "/artifacts",
                "score": 0.66,
                "signals": {
                    "docs_count": doc_count,
                    "deep_dossier_count": deep_dossier_count,
                },
            }
        )

    candidates.sort(
        key=lambda item: (
            _safe_float(item.get("score"), default=0.0),
            _safe_int((item.get("signals") or {}).get("overdue_tasks")),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return candidates[:8]


def _apply_recommendation_controls(
    candidates: list[dict[str, Any]],
    controls: dict[str, Any],
    *,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    dismissed_ids: set[str] = set(controls.get("dismissed_ids") or set())
    snoozed_until: dict[str, datetime] = dict(controls.get("snoozed_until") or {})
    muted_category_until: dict[str, datetime] = dict(controls.get("muted_category_until") or {})
    recently_presented_ids: set[str] = set(controls.get("recently_presented_ids") or set())
    category_not_useful_until: dict[str, datetime] = dict(controls.get("category_not_useful_until") or {})
    category_not_useful_count: dict[str, int] = dict(controls.get("category_not_useful_count") or {})

    visible: list[dict[str, Any]] = []
    for item in candidates:
        recommendation_id = str(item.get("id") or "").strip().lower()
        category = str(item.get("category") or "").strip().lower()
        if not recommendation_id:
            continue
        if recommendation_id in dismissed_ids:
            continue
        if (snoozed_until.get(recommendation_id) or datetime.min.replace(tzinfo=timezone.utc)) > now_utc:
            continue
        if (muted_category_until.get(category) or datetime.min.replace(tzinfo=timezone.utc)) > now_utc:
            continue
        if recommendation_id in recently_presented_ids:
            continue

        normalized_item = dict(item)
        normalized_signals = dict(normalized_item.get("signals") or {})
        base_score = min(1.0, max(0.0, _safe_float(normalized_item.get("score"), default=0.0)))
        score_penalty = 0.0
        penalty_until = category_not_useful_until.get(category)
        if penalty_until and penalty_until > now_utc:
            not_useful_count = max(1, _safe_int(category_not_useful_count.get(category), default=1))
            score_penalty = min(0.35, 0.18 * float(not_useful_count))
            normalized_signals["category_not_useful_count_recent"] = not_useful_count
            normalized_signals["category_feedback_penalty_applied"] = True
            why_this = str(normalized_item.get("why_this") or "").strip()
            fatigue_note = "Feedback recente desta categoria reduziu a prioridade da sugestao."
            if fatigue_note.lower() not in why_this.lower():
                normalized_item["why_this"] = f"{why_this} {fatigue_note}".strip()

        adjusted_score = min(1.0, max(0.0, base_score - score_penalty))
        normalized_item["score"] = round(adjusted_score, 4)
        normalized_signals["score_penalty"] = round(score_penalty, 4)
        normalized_item["signals"] = normalized_signals
        visible.append(normalized_item)

    visible.sort(
        key=lambda item: (
            _safe_float(item.get("score"), default=0.0),
            _safe_int((item.get("signals") or {}).get("overdue_tasks")),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return visible


@router.get("/pipeline/recommendations", response_model=ProactiveRecommendationsResponse)
async def list_proactive_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProactiveRecommendationsResponse:
    """Return ranked proactive recommendations with persistent control-state filtering."""
    _require_proactive_copilot_access(current_user)
    now_utc = datetime.now(timezone.utc)
    candidates = _build_proactive_recommendation_candidates(
        db,
        user_id=current_user.id,
        now_utc=now_utc,
    )
    controls = _load_recommendation_controls(
        db,
        user_id=current_user.id,
        now_utc=now_utc,
    )
    visible = _apply_recommendation_controls(
        candidates,
        controls,
        now_utc=now_utc,
    )

    recommendation_ids = [str(item.get("id") or "").strip().lower() for item in visible if item.get("id")]
    if recommendation_ids:
        crud.create_premium_analytics_event(
            db,
            user_id=current_user.id,
            event_type="recommendation.feed.generated",
            touchpoint="pipeline.recommendations_feed",
            capability="premium_proactive_copilot",
            metadata={
                "recommendation_ids": recommendation_ids,
                "categories": [str(item.get("category") or "").strip().lower() for item in visible],
                "count": len(recommendation_ids),
            },
        )

    emit_event(
        logger,
        "recommendation.feed.generated",
        category="recommendation",
        user_id=current_user.id,
        candidates=len(candidates),
        visible=len(visible),
    )

    return ProactiveRecommendationsResponse(
        generated_at=now_utc.isoformat(),
        recommendation_count=len(visible),
        recommendations=[ProactiveRecommendationItem(**item) for item in visible],
    )


@router.post("/pipeline/recommendations/actions", response_model=ProactiveRecommendationActionResponse)
async def record_proactive_recommendation_action(
    payload: ProactiveRecommendationActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProactiveRecommendationActionResponse:
    """Persist recommendation actions such as dismiss/snooze/mute/feedback."""
    _require_proactive_copilot_access(current_user)
    recommendation_id = str(payload.recommendation_id or "").strip().lower()
    if not recommendation_id:
        raise HTTPException(status_code=422, detail="recommendation_id is required.")

    action = str(payload.action or "").strip().lower()
    if action not in _RECOMMENDATION_ACTION_VALUES:
        raise HTTPException(status_code=422, detail=f"Unsupported recommendation action: {action}")

    category = str(payload.category or "").strip().lower() or None
    if category and category not in _RECOMMENDATION_CATEGORY_VALUES:
        raise HTTPException(status_code=422, detail=f"Unsupported recommendation category: {category}")
    if action == "mute_category" and not category:
        raise HTTPException(status_code=422, detail="category is required when action='mute_category'.")

    now_utc = datetime.now(timezone.utc)
    effective_until: str | None = None
    duration_hours = payload.duration_hours
    if action in {"snooze", "mute_category"}:
        default_hours = 24 if action == "snooze" else 24 * 7
        resolved_hours = int(duration_hours or default_hours)
        effective_until = (now_utc + timedelta(hours=resolved_hours)).isoformat()
        duration_hours = resolved_hours

    event_type_by_action: dict[str, str] = {
        "dismiss": "recommendation.dismissed",
        "snooze": "recommendation.snoozed",
        "mute_category": "recommendation.category_muted",
        "feedback_useful": "recommendation.feedback.recorded",
        "feedback_not_useful": "recommendation.feedback.recorded",
    }
    event_type = event_type_by_action[action]
    metadata = {
        "recommendation_id": recommendation_id,
        "category": category,
        "action": action,
        "duration_hours": duration_hours,
        "effective_until": effective_until,
        "feedback_note": payload.feedback_note,
        "useful": True if action == "feedback_useful" else (False if action == "feedback_not_useful" else None),
        "source": "dashboard",
    }

    crud.create_premium_analytics_event(
        db,
        user_id=current_user.id,
        event_type=event_type,
        touchpoint="dashboard.proactive_recommendations",
        capability="premium_proactive_copilot",
        metadata=metadata,
    )

    emit_event(
        logger,
        "recommendation.action.recorded",
        category="recommendation",
        user_id=current_user.id,
        recommendation_id=recommendation_id,
        recommendation_action=action,
        recommendation_category=category,
        effective_until=effective_until,
    )

    return ProactiveRecommendationActionResponse(
        action=payload.action,
        event_type=event_type,
        recommendation_id=recommendation_id,
        category=payload.category,
        effective_until=effective_until,
    )


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
    _require_proactive_copilot_access(current_user)
    import random
    from datetime import date

    today = date.today().isoformat()
    emit_event(
        logger,
        "recommendation.daily_question.requested",
        category="recommendation",
        user_id=current_user.id,
        date=today,
    )

    # Verifica cache diário
    existing = crud.get_daily_question_for_user(db, current_user.id, today)
    if existing:
        emit_event(
            logger,
            "recommendation.daily_question.cached",
            category="recommendation",
            user_id=current_user.id,
            date=today,
            doc_name=existing.doc_name,
        )
        return {
            "question": existing.question,
            "answer_hint": existing.answer_hint,
            "doc_name": existing.doc_name,
            "date": existing.date_generated,
        }

    docs = crud.list_documents_for_user(db, current_user.id)
    if not docs:
        emit_event(
            logger,
            "recommendation.daily_question.empty_docs",
            category="recommendation",
            user_id=current_user.id,
            date=today,
        )
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
        emit_event(
            logger,
            "recommendation.daily_question.failed",
            level="error",
            category="recommendation",
            user_id=current_user.id,
            date=today,
            error_type=exc.__class__.__name__,
        )
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
        emit_event(
            logger,
            "recommendation.daily_question.generated",
            category="recommendation",
            user_id=current_user.id,
            date=today,
            doc_name=doc.file_name,
        )
        return {
            "question": record.question,
            "answer_hint": record.answer_hint,
            "doc_name": record.doc_name,
            "date": record.date_generated,
        }

    emit_event(
        logger,
        "recommendation.daily_question.empty_result",
        category="recommendation",
        user_id=current_user.id,
        date=today,
        doc_name=doc.file_name,
    )
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
    _require_proactive_copilot_access(current_user)
    docs = crud.list_documents_for_user(db, current_user.id)
    if not docs:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado.")

    target_count = len([d for d in docs if not payload.doc_names or d.file_name in payload.doc_names]) or len(docs)
    emit_event(
        logger,
        "recommendation.gap_analysis.started",
        category="recommendation",
        user_id=current_user.id,
        target_docs=min(target_count, 3),
        selected_doc_filters=len(payload.doc_names or []),
    )
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
        logger.exception("Falha na gap analysis: %s", exc)
        emit_event(
            logger,
            "recommendation.gap_analysis.failed",
            level="error",
            category="recommendation",
            user_id=current_user.id,
            error_type=exc.__class__.__name__,
        )
        raise HTTPException(status_code=500, detail="Erro interno ao executar análise de lacunas.")

    emit_event(
        logger,
        "recommendation.gap_analysis.completed",
        category="recommendation",
        user_id=current_user.id,
        target_docs=min(target_count, 3),
        gap_count=len(gaps_raw),
    )
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
    """Evaluate a user answer for the daily-question flow."""
    _require_proactive_copilot_access(current_user)
    try:
        feedback, score = await asyncio.to_thread(
            _run_evaluate_answer,
            payload.question,
            payload.user_answer,
            payload.answer_hint,
        )
    except Exception as exc:
        logger.exception("Falha ao avaliar resposta: %s", exc)
        raise HTTPException(status_code=500, detail="Erro interno ao avaliar resposta.")

    return EvaluateAnswerResponse(feedback=feedback, score=score)

