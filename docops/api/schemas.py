"""Pydantic request/response models for the DocOps Agent API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional
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


class GoogleAuthRequest(BaseModel):
    access_token: str


class GoogleAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
    doc_id: str = ""
    file_name: str
    source: str
    chunk_count: int


# ── /api/chat ─────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """A single turn in the conversation history."""
    role: str  # "user" | "assistant"
    content: str


class ActiveChatContext(BaseModel):
    """Short-lived operational context for a chat session."""
    active_doc_ids: List[str] = Field(default_factory=list)
    active_doc_names: List[str] = Field(default_factory=list)
    active_deck_id: Optional[int] = None
    active_deck_title: Optional[str] = None
    active_task_id: Optional[int] = None
    active_task_title: Optional[str] = None
    active_note_id: Optional[int] = None
    active_note_title: Optional[str] = None
    active_intent: Optional[str] = None
    last_action: Optional[str] = None
    last_user_command: Optional[str] = None
    last_card_count: Optional[int] = None
    last_difficulty_mix: Optional[dict[str, int]] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    doc_names: List[str] = Field(default_factory=list)
    debug_grounding: bool = False
    strict_grounding: bool = False
    # Últimas N mensagens do histórico (frontend envia para dar contexto ao backend)
    history: List[ChatMessage] = Field(default_factory=list)
    active_context: Optional[ActiveChatContext] = None


class ChatQualitySignal(BaseModel):
    level: str = Field(description="high | medium | low")
    score: float = Field(ge=0.0, le=1.0)
    label: str
    reasons: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    score_components: dict[str, float] = Field(default_factory=dict)
    support_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    unsupported_claim_count: int = 0
    suggested_action: Optional[str] = None
    source_count: int = 0
    retrieved_count: int = 0


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    intent: str
    session_id: Optional[str] = None
    grounding: Optional[dict[str, Any]] = None
    calendar_action: Optional[dict[str, Any]] = None
    action_metadata: Optional[dict[str, Any]] = None
    needs_confirmation: bool = False
    confirmation_text: Optional[str] = None
    suggested_reply: Optional[str] = None
    active_context: Optional[ActiveChatContext] = None
    quality_signal: Optional[ChatQualitySignal] = None


# ── /api/capabilities ─────────────────────────────────────────────────────────

class CapabilityFlag(BaseModel):
    key: str
    enabled: bool
    env_var: str
    default_enabled: bool
    description: str
    owner: str


class CapabilitiesResponse(BaseModel):
    flags: List[CapabilityFlag] = Field(default_factory=list)
    map: dict[str, bool] = Field(default_factory=dict)
    disable_all: bool = False
    enable_all: bool = False


# -- /api/preferences ---------------------------------------------------------

PreferenceDefaultDepth = Literal["brief", "balanced", "deep"]
PreferenceTone = Literal["neutral", "didactic", "objective", "encouraging"]
PreferenceStrictness = Literal["relaxed", "balanced", "strict"]
PreferenceSchedule = Literal["flexible", "fixed", "intensive"]


class UserPreferencesResponse(BaseModel):
    schema_version: int = Field(ge=1)
    default_depth: PreferenceDefaultDepth
    tone: PreferenceTone
    strictness_preference: PreferenceStrictness
    schedule_preference: PreferenceSchedule


class UserPreferencesUpdateRequest(BaseModel):
    default_depth: Optional[PreferenceDefaultDepth] = None
    tone: Optional[PreferenceTone] = None
    strictness_preference: Optional[PreferenceStrictness] = None
    schedule_preference: Optional[PreferenceSchedule] = None


# ── /api/summarize ────────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    doc: str = Field(min_length=1, description="Document file name to summarize")
    save: bool = False
    summary_mode: str = Field(
        default="brief",
        description="'brief' for a short synthesis, 'deep' for a full detailed analysis",
    )
    template_id: Optional[str] = Field(
        default=None,
        description="Artifact template id (brief | exam_pack | deep_dossier).",
    )
    debug_summary: bool = Field(
        default=False,
        description="When true and summary_mode='deep', include summary diagnostics in response.",
    )
    deep_profile: Optional[str] = Field(
        default=None,
        description=(
            "Execution profile for deep summary: 'fast' | 'balanced' | 'model_first' | "
            "'model_first_plus' | 'model_first_plus_max' | 'strict'. "
            "When None, uses SUMMARY_DEEP_PROFILE (default: 'balanced')."
        ),
    )


class SummarizeResponse(BaseModel):
    answer: str
    artifact_path: Optional[str] = None
    artifact_filename: Optional[str] = None
    template_id: Optional[str] = None
    template_label: Optional[str] = None
    template_description: Optional[str] = None
    summary_diagnostics: Optional[dict[str, Any]] = None


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
    doc_names: List[str] = Field(
        default_factory=list,
        description="Optional list of document names/ids to constrain generation",
    )
    output: Optional[str] = None
    template_id: Optional[str] = Field(
        default=None,
        description="Artifact template id (brief | exam_pack | deep_dossier).",
    )


class ArtifactResponse(BaseModel):
    answer: str
    filename: str
    path: str
    template_id: Optional[str] = None
    template_label: Optional[str] = None
    template_description: Optional[str] = None
    artifact_id: Optional[int] = None


class ChatArtifactCreateRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=200_000)
    title: Optional[str] = Field(default=None, max_length=512)
    user_prompt: Optional[str] = Field(default=None, max_length=4096)
    session_id: Optional[str] = Field(default=None, max_length=128)
    turn_ref: Optional[str] = Field(default=None, max_length=64)
    doc_ids: List[str] = Field(default_factory=list)
    doc_names: List[str] = Field(default_factory=list)
    template_id: Optional[str] = Field(
        default=None,
        description="Artifact template id (brief | exam_pack | deep_dossier).",
    )
    artifact_type: str = Field(default="summary", max_length=64)
    generation_profile: Optional[str] = Field(default=None, max_length=128)
    confidence_level: Optional[str] = Field(default=None, max_length=16)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ChatArtifactCreateResponse(ArtifactResponse):
    conversation_session_id: Optional[str] = None
    conversation_turn_ref: Optional[str] = None


class ArtifactTemplateItem(BaseModel):
    template_id: str
    label: str
    short_description: str
    long_description: str
    preview_title: str
    preview_sections: List[str] = Field(default_factory=list)
    artifact_types: List[str] = Field(default_factory=list)
    summary_modes: List[str] = Field(default_factory=list)
    default_for_summary_modes: List[str] = Field(default_factory=list)
    default_for_artifact_types: List[str] = Field(default_factory=list)


# ── /api/artifacts ────────────────────────────────────────────────────────────

class ArtifactItem(BaseModel):
    id: int
    filename: str
    size: int
    created_at: str
    artifact_type: str = ""
    title: Optional[str] = None
    template_id: Optional[str] = None
    generation_profile: Optional[str] = None
    confidence_level: Optional[str] = None
    confidence_score: Optional[float] = None
    metadata_version: int = 1
    source_doc_ids: List[str] = Field(default_factory=list)
    source_doc_count: int = 0
    conversation_session_id: Optional[str] = None
    conversation_turn_ref: Optional[str] = None


class ArtifactFilterOptionsResponse(BaseModel):
    artifact_types: List[str] = Field(default_factory=list)
    template_ids: List[str] = Field(default_factory=list)
    generation_profiles: List[str] = Field(default_factory=list)
    source_doc_ids: List[str] = Field(default_factory=list)
    confidence_levels: List[str] = Field(default_factory=list)


# ── /api/health ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class ReadinessCheck(BaseModel):
    ok: bool
    detail: str = "ok"


class ReadyResponse(BaseModel):
    status: str = "ok"
    checks: dict[str, ReadinessCheck]


# -- /api/jobs ----------------------------------------------------------------

class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    stage: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    stage: str
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


# -- /api/calendar ------------------------------------------------------------

class ReminderCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    ends_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=2048)
    all_day: bool = False


class ReminderUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    ends_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=2048)
    all_day: bool = False


class ReminderItem(BaseModel):
    id: int
    title: str
    starts_at: datetime
    ends_at: Optional[datetime] = None
    note: Optional[str] = None
    all_day: bool = False


class ScheduleCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    note: Optional[str] = Field(default=None, max_length=1024)
    active: bool = True


class ScheduleUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    note: Optional[str] = Field(default=None, max_length=1024)
    active: bool = True


class ScheduleItem(BaseModel):
    id: int
    title: str
    day_of_week: int
    start_time: str
    end_time: str
    note: Optional[str] = None
    active: bool


class CalendarOverviewResponse(BaseModel):
    date: str
    now_iso: str
    today_reminders: List[ReminderItem]
    today_schedule: List[ScheduleItem]
    current_schedule_item: Optional[ScheduleItem] = None
    next_schedule_item: Optional[ScheduleItem] = None
