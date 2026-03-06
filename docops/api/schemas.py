"""Pydantic request/response models for the DocOps Agent API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")


class RegisterResponse(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime


# ── Common ────────────────────────────────────────────────────────────────────

class SourceItem(BaseModel):
    """A single cited source chunk."""
    fonte_n: int = Field(description="Citation number (1-indexed)")
    file_name: str
    page: str = Field(default="N/A")
    section_path: str = Field(default="")
    snippet: str
    chunk_id: str = Field(default="")


# ── /api/ingest ───────────────────────────────────────────────────────────────

class IngestPathRequest(BaseModel):
    """Request body for ingesting a local directory or file path."""
    path: str = Field(description="Absolute or relative path on the server")
    chunk_size: int = Field(default=0, ge=0)
    chunk_overlap: int = Field(default=0, ge=0)


class IngestResponse(BaseModel):
    files_loaded: int
    chunks_indexed: int
    file_names: List[str]


# ── /api/docs ─────────────────────────────────────────────────────────────────

class DocItem(BaseModel):
    file_name: str
    source: str
    chunk_count: int


# ── /api/chat ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    debug_grounding: bool = False


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    intent: str
    session_id: Optional[str] = None
    grounding: Optional[dict[str, Any]] = None


# ── /api/summarize ────────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    doc: str = Field(min_length=1, description="Document file name to summarize")
    save: bool = False
    summary_mode: str = Field(
        default="brief",
        description="'brief' for a short synthesis, 'deep' for a full detailed analysis",
    )


class SummarizeResponse(BaseModel):
    answer: str
    artifact_path: Optional[str] = None


# ── /api/compare ──────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    doc1: str = Field(min_length=1)
    doc2: str = Field(min_length=1)
    save: bool = False


class CompareResponse(BaseModel):
    answer: str
    artifact_path: Optional[str] = None


# ── /api/artifact ─────────────────────────────────────────────────────────────

class ArtifactRequest(BaseModel):
    type: str = Field(description="study_plan | summary | checklist | artifact")
    topic: str = Field(min_length=1)
    output: Optional[str] = None


class ArtifactResponse(BaseModel):
    answer: str
    filename: str
    path: str


# ── /api/artifacts ────────────────────────────────────────────────────────────

class ArtifactItem(BaseModel):
    filename: str
    size: int
    created_at: str


# ── /api/health ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
