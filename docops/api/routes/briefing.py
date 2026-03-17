"""Rota de morning briefing — /api/briefing."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class BriefingTask(BaseModel):
    id: int
    title: str
    priority: str
    due_date: datetime | None

class BriefingReminder(BaseModel):
    id: int
    title: str
    starts_at: str
    all_day: bool
    note: str | None

class BriefingScheduleItem(BaseModel):
    title: str
    start_time: str
    end_time: str

class BriefingResponse(BaseModel):
    date: str          # ISO date string
    greeting: str      # "Bom dia", "Boa tarde", "Boa noite"
    today_reminders: list[BriefingReminder]
    today_schedule: list[BriefingScheduleItem]
    pending_tasks: list[BriefingTask]
    overdue_tasks: list[BriefingTask]
    docs_count: int
    notes_count: int


def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 12:
        return "Bom dia"
    if h < 18:
        return "Boa tarde"
    return "Boa noite"


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/briefing", response_model=BriefingResponse)
def get_briefing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Lembretes de hoje
    reminders = crud.list_reminders_for_user(db, current_user.id, start_from=today_start, end_to=today_end)
    today_reminders = [
        BriefingReminder(
            id=r.id,
            title=r.title,
            starts_at=r.starts_at.isoformat(),
            all_day=r.all_day,
            note=r.note,
        )
        for r in reminders
    ]

    # Cronograma de hoje (dia da semana)
    dow = now.weekday()  # 0=Monday
    schedules = crud.list_schedules_for_user(db, current_user.id, active_only=True)
    today_schedule = [
        BriefingScheduleItem(title=s.title, start_time=s.start_time, end_time=s.end_time)
        for s in schedules
        if s.day_of_week == dow
    ]

    # Tarefas pendentes (não concluídas)
    all_tasks = crud.list_tasks_for_user(db, current_user.id)
    pending = [t for t in all_tasks if t.status != "done"]
    overdue = [
        t for t in pending
        if t.due_date is not None and t.due_date < now
    ]
    pending_not_overdue = [t for t in pending if t not in overdue]

    pending_tasks = [
        BriefingTask(id=t.id, title=t.title, priority=t.priority, due_date=t.due_date)
        for t in sorted(pending_not_overdue, key=lambda t: (t.priority != "high", t.created_at))[:5]
    ]
    overdue_tasks = [
        BriefingTask(id=t.id, title=t.title, priority=t.priority, due_date=t.due_date)
        for t in overdue[:5]
    ]

    # Contagens
    docs_count = len(crud.list_documents_for_user(db, current_user.id))
    notes_count = len(crud.list_notes_for_user(db, current_user.id))

    return BriefingResponse(
        date=now.date().isoformat(),
        greeting=_greeting(now),
        today_reminders=today_reminders,
        today_schedule=today_schedule,
        pending_tasks=pending_tasks,
        overdue_tasks=overdue_tasks,
        docs_count=docs_count,
        notes_count=notes_count,
    )
