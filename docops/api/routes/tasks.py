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
    checklist_done: int = 0
    checklist_total: int = 0

    class Config:
        from_attributes = True


class ChecklistItemCreate(BaseModel):
    text: str = Field(min_length=1, max_length=512)


class ChecklistItemUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=512)
    done: Optional[bool] = None


class ChecklistItemResponse(BaseModel):
    id: int
    task_id: int
    text: str
    done: bool
    position: int
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2048)


class ActivityResponse(BaseModel):
    id: int
    task_id: int
    text: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(task: "crud.TaskRecord") -> TaskResponse:
    items = task.checklist_items
    total = len(items)
    done = sum(1 for i in items if i.done)
    return TaskResponse(
        id=task.id,
        title=task.title,
        note=task.note,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        checklist_done=done,
        checklist_total=total,
    )


# ── Task endpoints ─────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = crud.list_tasks_for_user(db, current_user.id, status=status)
    return [_to_response(t) for t in tasks]


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.create_task_record(
        db,
        user_id=current_user.id,
        title=payload.title,
        note=payload.note,
        priority=payload.priority,
        due_date=payload.due_date,
    )
    return _to_response(task)


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
    task = crud.update_task_record(
        db, task,
        title=payload.title,
        note=payload.note,
        status=payload.status,
        priority=payload.priority,
        due_date=payload.due_date,
    )
    return _to_response(task)


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


# ── Checklist endpoints ────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}/checklist", response_model=list[ChecklistItemResponse])
def list_checklist(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return crud.list_task_checklist_items(db, task_id)


@router.post("/tasks/{task_id}/checklist", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
def create_checklist_item(
    task_id: int,
    payload: ChecklistItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    existing = crud.list_task_checklist_items(db, task_id)
    return crud.create_task_checklist_item(db, task_id=task_id, text=payload.text, position=len(existing))


@router.put("/tasks/{task_id}/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    task_id: int,
    item_id: int,
    payload: ChecklistItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    item = crud.get_task_checklist_item(db, item_id, task_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return crud.update_task_checklist_item(db, item, text=payload.text, done=payload.done)


@router.delete("/tasks/{task_id}/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    task_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    item = crud.get_task_checklist_item(db, item_id, task_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    crud.delete_task_checklist_item(db, item)


# ── Activity log endpoints ─────────────────────────────────────────────────────

@router.get("/tasks/{task_id}/activities", response_model=list[ActivityResponse])
def list_activities(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return crud.list_task_activities(db, task_id)


@router.post("/tasks/{task_id}/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    task_id: int,
    payload: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return crud.create_task_activity(db, task_id=task_id, text=payload.text)


@router.delete("/tasks/{task_id}/activities/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    task_id: int,
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_user_and_id(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    activity = crud.get_task_activity(db, log_id, task_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    crud.delete_task_activity(db, activity)
