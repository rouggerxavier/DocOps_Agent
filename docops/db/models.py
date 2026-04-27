"""Modelos SQLAlchemy."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docops.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    documents: Mapped[list[DocumentRecord]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    artifacts: Mapped[list[ArtifactRecord]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    reminders: Mapped[list[ReminderRecord]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    schedules: Mapped[list[ScheduleRecord]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    notes: Mapped[list[NoteRecord]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    tasks: Mapped[list[TaskRecord]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    flashcard_decks: Mapped[list[FlashcardDeck]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    study_plans: Mapped[list["StudyPlanRecord"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    daily_questions: Mapped[list["DailyQuestionRecord"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    reading_status_records: Mapped[list["ReadingStatusRecord"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    premium_analytics_events: Mapped[list["PremiumAnalyticsEventRecord"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    preferences: Mapped["UserPreferenceRecord | None"] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        uselist=False,
    )
    onboarding_state: Mapped["UserOnboardingStateRecord | None"] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        uselist=False,
    )
    onboarding_events: Mapped[list["UserOnboardingEventRecord"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="documents")

    __table_args__ = (
        UniqueConstraint("user_id", "doc_id", name="uq_user_doc"),
        Index("ix_user_doc", "user_id", "doc_id"),
    )

    def __repr__(self) -> str:
        return f"<DocumentRecord id={self.id} user={self.user_id} file={self.file_name!r}>"


class UserPreferenceRecord(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    default_depth: Mapped[str] = mapped_column(String(16), nullable=False, default="brief")
    tone: Mapped[str] = mapped_column(String(16), nullable=False, default="neutral")
    strictness_preference: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    schedule_preference: Mapped[str] = mapped_column(String(16), nullable=False, default="flexible")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="preferences")

    __table_args__ = (
        Index("ix_user_preferences_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<UserPreferenceRecord id={self.id} user={self.user_id} schema={self.schema_version}>"


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_doc_id_2: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_doc_ids: Mapped[str | None] = mapped_column(String(512), nullable=True)
    conversation_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conversation_turn_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("ix_artifact_user_filename", "user_id", "filename"),
        Index("ix_artifact_user_type", "user_id", "artifact_type"),
        Index("ix_artifact_user_template", "user_id", "template_id"),
        Index("ix_artifact_user_created", "user_id", "created_at"),
        Index("ix_artifact_user_confidence", "user_id", "confidence_score"),
        Index("ix_artifact_user_conversation", "user_id", "conversation_session_id"),
    )

    def __repr__(self) -> str:
        return f"<ArtifactRecord id={self.id} user={self.user_id} file={self.filename!r}>"


class ReminderRecord(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="reminders")

    __table_args__ = (
        Index("ix_reminder_user_starts_at", "user_id", "starts_at"),
    )

    def __repr__(self) -> str:
        return f"<ReminderRecord id={self.id} user={self.user_id} title={self.title!r}>"


class ScheduleRecord(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 0=Monday ... 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="schedules")

    __table_args__ = (
        Index("ix_schedule_user_day", "user_id", "day_of_week"),
    )

    def __repr__(self) -> str:
        return f"<ScheduleRecord id={self.id} user={self.user_id} title={self.title!r}>"


class NoteRecord(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="notes")

    __table_args__ = (
        Index("ix_note_user_updated", "user_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<NoteRecord id={self.id} user={self.user_id} title={self.title!r}>"


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    note: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending | doing | done
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")  # low | normal | high
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="tasks")
    checklist_items: Mapped[list["TaskChecklistItem"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="TaskChecklistItem.position, TaskChecklistItem.created_at",
    )
    activity_logs: Mapped[list["TaskActivityLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="TaskActivityLog.created_at",
    )

    __table_args__ = (
        Index("ix_task_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<TaskRecord id={self.id} user={self.user_id} title={self.title!r} status={self.status!r}>"


class TaskChecklistItem(Base):
    __tablename__ = "task_checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    task: Mapped["TaskRecord"] = relationship(back_populates="checklist_items")

    def __repr__(self) -> str:
        return f"<TaskChecklistItem id={self.id} task={self.task_id} done={self.done}>"


class TaskActivityLog(Base):
    __tablename__ = "task_activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    task: Mapped["TaskRecord"] = relationship(back_populates="activity_logs")

    def __repr__(self) -> str:
        return f"<TaskActivityLog id={self.id} task={self.task_id}>"


class FlashcardDeck(Base):
    __tablename__ = "flashcard_decks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_doc: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="flashcard_decks")
    cards: Mapped[list["FlashcardItem"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
        order_by="FlashcardItem.id.asc()",
    )

    def __repr__(self) -> str:
        return f"<FlashcardDeck id={self.id} title={self.title!r}>"


class FlashcardItem(Base):
    __tablename__ = "flashcard_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(Integer, ForeignKey("flashcard_decks.id"), nullable=False, index=True)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), default="media", nullable=False)  # facil, media, dificil
    ease: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=new, 1=hard, 2=good, 3=easy
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deck: Mapped[FlashcardDeck] = relationship(back_populates="cards")

    def __repr__(self) -> str:
        return f"<FlashcardItem id={self.id} deck={self.deck_id} front={self.front[:30]!r}>"


class StudyPlanRecord(Base):
    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_name: Mapped[str] = mapped_column(String(512), nullable=False)
    plan_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tasks_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reminders_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deck_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hours_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    deadline_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="study_plans")

    __table_args__ = (
        Index("ix_study_plan_user", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<StudyPlanRecord id={self.id} user={self.user_id} doc={self.doc_name!r}>"


class DailyQuestionRecord(Base):
    __tablename__ = "daily_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_hint: Mapped[str] = mapped_column(Text, nullable=False, default="")
    doc_name: Mapped[str] = mapped_column(String(512), nullable=False)
    date_generated: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="daily_questions")

    __table_args__ = (
        Index("ix_daily_question_user_date", "user_id", "date_generated"),
    )

    def __repr__(self) -> str:
        return f"<DailyQuestionRecord id={self.id} user={self.user_id} date={self.date_generated!r}>"


class ReadingStatusRecord(Base):
    __tablename__ = "reading_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="to_read")  # to_read | reading | done
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="reading_status_records")

    __table_args__ = (
        UniqueConstraint("user_id", "doc_id", name="uq_user_doc_reading"),
    )

    def __repr__(self) -> str:
        return f"<ReadingStatusRecord id={self.id} user={self.user_id} doc={self.doc_id!r} status={self.status!r}>"


class UserOnboardingStateRecord(Base):
    __tablename__ = "user_onboarding_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    welcome_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tour_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tour_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tour_skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step_completions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    section_skips: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_step_seen: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="onboarding_state")

    def __repr__(self) -> str:
        return f"<UserOnboardingStateRecord id={self.id} user={self.user_id} schema={self.schema_version}>"


class UserOnboardingEventRecord(Base):
    __tablename__ = "user_onboarding_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    owner: Mapped[User] = relationship(back_populates="onboarding_events")

    __table_args__ = (
        Index("ix_onboarding_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_onboarding_events_event_occurred", "event_type", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            "<UserOnboardingEventRecord "
            f"id={self.id} user={self.user_id} event={self.event_type!r} step={self.step_id!r}>"
        )


class PremiumAnalyticsEventRecord(Base):
    __tablename__ = "premium_analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    touchpoint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    capability: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    owner: Mapped["User"] = relationship(back_populates="premium_analytics_events")

    __table_args__ = (
        Index("ix_premium_analytics_touchpoint_created", "touchpoint", "created_at"),
        Index("ix_premium_analytics_event_created", "event_type", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            "<PremiumAnalyticsEventRecord "
            f"id={self.id} user={self.user_id} event={self.event_type!r} touchpoint={self.touchpoint!r}>"
        )
