"""Rotas de notas rápidas — /api/notes."""

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

class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(default="", max_length=200_000)
    pinned: bool = False


class NoteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(default="", max_length=200_000)
    pinned: bool = False


class NoteResponse(BaseModel):
    id: int
    title: str
    content: str
    pinned: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/notes", response_model=list[NoteResponse])
def list_notes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.list_notes_for_user(db, current_user.id)


@router.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_note_record(
        db,
        user_id=current_user.id,
        title=payload.title,
        content=payload.content,
        pinned=payload.pinned,
    )


@router.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = crud.get_note_by_user_and_id(db, current_user.id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return crud.update_note_record(
        db, note,
        title=payload.title,
        content=payload.content,
        pinned=payload.pinned,
    )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = crud.get_note_by_user_and_id(db, current_user.id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    crud.delete_note_record(db, note)
