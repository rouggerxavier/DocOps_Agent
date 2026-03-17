"""Rotas de tarefas — /api/tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    note: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    note: Optional[str] = None
    status: str = Field(default="pending", pattern="^(pending|doing|done)$")
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    due_date: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: int
    title: str
    note: Optional[str]
    status: str
    priority: str
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.list_tasks_for_user(db, current_user.id, status=status)


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_task_record(
        db,
        user_id=current_user.id,
        title=payload.title,
        note=payload.note,
        priority=payload.priority,
        due_date=payload.due_date,
    )


@router.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return crud.update_task_record(
        db, task,
        title=payload.title,
        note=payload.note,
        status=payload.status,
        priority=payload.priority,
        due_date=payload.due_date,
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    crud.delete_task_record(db, task)
