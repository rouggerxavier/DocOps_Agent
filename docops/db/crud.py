"""CRUD helpers for SQL models."""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata

from sqlalchemy import or_
from sqlalchemy.orm import Session

from docops.db.models import ArtifactRecord, DocumentRecord, ReminderRecord, ScheduleRecord, User


# -- User --------------------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, name: str, email: str, password_hash: str) -> User:
    user = User(name=name, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# -- DocumentRecord -----------------------------------------------------------

def create_document_record(
    db: Session,
    *,
    user_id: int,
    doc_id: str,
    file_name: str,
    source_path: str,
    storage_path: str,
    file_type: str,
    chunk_count: int = 0,
    original_filename: str | None = None,
    sha256_hash: str | None = None,
) -> DocumentRecord:
    existing = get_document_by_user_and_doc_id(db, user_id, doc_id)
    if existing:
        existing.file_name = file_name
        existing.source_path = source_path
        existing.storage_path = storage_path
        existing.file_type = file_type
        existing.chunk_count = chunk_count
        if original_filename is not None:
            existing.original_filename = original_filename
        if sha256_hash is not None:
            existing.sha256_hash = sha256_hash
        db.commit()
        db.refresh(existing)
        return existing

    doc = DocumentRecord(
        user_id=user_id,
        doc_id=doc_id,
        file_name=file_name,
        original_filename=original_filename,
        source_path=source_path,
        storage_path=storage_path,
        file_type=file_type,
        chunk_count=chunk_count,
        sha256_hash=sha256_hash,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_document_by_user_and_doc_id(db: Session, user_id: int, doc_id: str) -> DocumentRecord | None:
    return (
        db.query(DocumentRecord)
        .filter(DocumentRecord.user_id == user_id, DocumentRecord.doc_id == doc_id)
        .first()
    )


def get_document_by_user_and_file_name(db: Session, user_id: int, file_name: str) -> DocumentRecord | None:
    return (
        db.query(DocumentRecord)
        .filter(DocumentRecord.user_id == user_id, DocumentRecord.file_name == file_name)
        .first()
    )


def list_documents_for_user(db: Session, user_id: int) -> list[DocumentRecord]:
    return (
        db.query(DocumentRecord)
        .filter(DocumentRecord.user_id == user_id)
        .order_by(DocumentRecord.created_at.desc())
        .all()
    )


def delete_document_record(db: Session, user_id: int, doc_id: str) -> bool:
    doc = get_document_by_user_and_doc_id(db, user_id, doc_id)
    if doc:
        db.delete(doc)
        db.commit()
        return True
    return False


# -- ArtifactRecord -----------------------------------------------------------

def _normalize_source_doc_ids(source_doc_ids: list[str] | None) -> str | None:
    if not source_doc_ids:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in source_doc_ids:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    if not normalized:
        return None
    # Pipe-delimited with leading/trailing marker allows exact-ish LIKE match.
    return f"|{'|'.join(normalized)}|"


def parse_source_doc_ids_blob(blob: str | None) -> list[str]:
    value = str(blob or "").strip()
    if not value:
        return []
    if value.startswith("|") and value.endswith("|"):
        return [item for item in value.strip("|").split("|") if item]
    return [item for item in value.split(",") if item]


def create_artifact_record(
    db: Session,
    *,
    user_id: int,
    artifact_type: str,
    filename: str,
    path: str,
    title: str | None = None,
    template_id: str | None = None,
    generation_profile: str | None = None,
    confidence_level: str | None = None,
    confidence_score: float | None = None,
    metadata_version: int = 1,
    source_doc_id: str | None = None,
    source_doc_id_2: str | None = None,
    source_doc_ids: list[str] | None = None,
    conversation_session_id: str | None = None,
    conversation_turn_ref: str | None = None,
) -> ArtifactRecord:
    source_doc_ids_blob = _normalize_source_doc_ids(source_doc_ids)
    artifact = ArtifactRecord(
        user_id=user_id,
        artifact_type=artifact_type,
        title=title,
        filename=filename,
        path=path,
        template_id=template_id,
        generation_profile=generation_profile,
        confidence_level=confidence_level,
        confidence_score=confidence_score,
        metadata_version=max(1, int(metadata_version or 1)),
        source_doc_id=source_doc_id,
        source_doc_id_2=source_doc_id_2,
        source_doc_ids=source_doc_ids_blob,
        conversation_session_id=str(conversation_session_id or "").strip() or None,
        conversation_turn_ref=str(conversation_turn_ref or "").strip() or None,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def list_artifacts_for_user(
    db: Session,
    user_id: int,
    *,
    artifact_type: str | None = None,
    source_doc_id: str | None = None,
    conversation_session_id: str | None = None,
    template_id: str | None = None,
    generation_profile: str | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list[ArtifactRecord]:
    query = db.query(ArtifactRecord).filter(ArtifactRecord.user_id == user_id)

    if artifact_type:
        query = query.filter(ArtifactRecord.artifact_type == artifact_type)
    if template_id:
        query = query.filter(ArtifactRecord.template_id == template_id)
    if conversation_session_id:
        query = query.filter(ArtifactRecord.conversation_session_id == conversation_session_id)
    if generation_profile:
        query = query.filter(ArtifactRecord.generation_profile == generation_profile)
    if source_doc_id:
        source_doc_id = str(source_doc_id).strip()
        if source_doc_id:
            query = query.filter(
                or_(
                    ArtifactRecord.source_doc_id == source_doc_id,
                    ArtifactRecord.source_doc_id_2 == source_doc_id,
                    ArtifactRecord.source_doc_ids.like(f"%|{source_doc_id}|%"),
                )
            )
    if search:
        term = f"%{str(search).strip()}%"
        query = query.filter(
            or_(
                ArtifactRecord.title.ilike(term),
                ArtifactRecord.filename.ilike(term),
            )
        )

    sort_key = str(sort_by or "created_at").strip().lower()
    sort_dir = str(sort_order or "desc").strip().lower()
    sort_map = {
        "created_at": ArtifactRecord.created_at,
        "updated_at": ArtifactRecord.updated_at,
        "title": ArtifactRecord.title,
        "artifact_type": ArtifactRecord.artifact_type,
        "confidence_score": ArtifactRecord.confidence_score,
        "filename": ArtifactRecord.filename,
    }
    sort_column = sort_map.get(sort_key, ArtifactRecord.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc(), ArtifactRecord.id.asc())
    else:
        query = query.order_by(sort_column.desc(), ArtifactRecord.id.desc())

    return query.all()


def list_artifact_filter_options_for_user(db: Session, user_id: int) -> dict[str, list[str]]:
    records = (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.user_id == user_id)
        .all()
    )

    artifact_types: set[str] = set()
    template_ids: set[str] = set()
    generation_profiles: set[str] = set()
    source_doc_ids: set[str] = set()
    confidence_levels: set[str] = set()

    for record in records:
        if record.artifact_type:
            artifact_types.add(str(record.artifact_type))
        if record.template_id:
            template_ids.add(str(record.template_id))
        if record.generation_profile:
            generation_profiles.add(str(record.generation_profile))
        if record.confidence_level:
            confidence_levels.add(str(record.confidence_level))

        raw_source_ids = [record.source_doc_id, record.source_doc_id_2] + parse_source_doc_ids_blob(record.source_doc_ids)
        for source_id in raw_source_ids:
            value = str(source_id or "").strip()
            if value:
                source_doc_ids.add(value)

    return {
        "artifact_types": sorted(artifact_types),
        "template_ids": sorted(template_ids),
        "generation_profiles": sorted(generation_profiles),
        "source_doc_ids": sorted(source_doc_ids),
        "confidence_levels": sorted(confidence_levels),
    }


def get_artifact_by_user_and_filename(db: Session, user_id: int, filename: str) -> ArtifactRecord | None:
    return (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.user_id == user_id, ArtifactRecord.filename == filename)
        .order_by(ArtifactRecord.created_at.desc(), ArtifactRecord.id.desc())
        .first()
    )


def list_artifacts_by_user_and_filename(db: Session, user_id: int, filename: str) -> list[ArtifactRecord]:
    return (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.user_id == user_id, ArtifactRecord.filename == filename)
        .order_by(ArtifactRecord.created_at.desc(), ArtifactRecord.id.desc())
        .all()
    )


def get_artifact_by_user_and_id(db: Session, user_id: int, artifact_id: int) -> ArtifactRecord | None:
    return (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.user_id == user_id, ArtifactRecord.id == artifact_id)
        .first()
    )


# -- ReminderRecord -----------------------------------------------------------

def create_reminder_record(
    db: Session,
    *,
    user_id: int,
    title: str,
    starts_at: datetime,
    ends_at: datetime | None = None,
    note: str | None = None,
    all_day: bool = False,
) -> ReminderRecord:
    reminder = ReminderRecord(
        user_id=user_id,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        note=note,
        all_day=all_day,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def get_reminder_by_user_and_id(db: Session, user_id: int, reminder_id: int) -> ReminderRecord | None:
    return (
        db.query(ReminderRecord)
        .filter(ReminderRecord.user_id == user_id, ReminderRecord.id == reminder_id)
        .first()
    )


def list_reminders_for_user(
    db: Session,
    user_id: int,
    *,
    start_from: datetime | None = None,
    end_to: datetime | None = None,
) -> list[ReminderRecord]:
    query = db.query(ReminderRecord).filter(ReminderRecord.user_id == user_id)
    if start_from is not None:
        query = query.filter(ReminderRecord.starts_at >= start_from)
    if end_to is not None:
        query = query.filter(ReminderRecord.starts_at <= end_to)
    return query.order_by(ReminderRecord.starts_at.asc()).all()


def update_reminder_record(
    db: Session,
    reminder: ReminderRecord,
    *,
    title: str,
    starts_at: datetime,
    ends_at: datetime | None = None,
    note: str | None = None,
    all_day: bool = False,
) -> ReminderRecord:
    reminder.title = title
    reminder.starts_at = starts_at
    reminder.ends_at = ends_at
    reminder.note = note
    reminder.all_day = all_day
    db.commit()
    db.refresh(reminder)
    return reminder


def delete_reminder_record(db: Session, reminder: ReminderRecord) -> None:
    db.delete(reminder)
    db.commit()


# -- ScheduleRecord -----------------------------------------------------------

def create_schedule_record(
    db: Session,
    *,
    user_id: int,
    title: str,
    day_of_week: int,
    start_time: str,
    end_time: str,
    note: str | None = None,
    active: bool = True,
) -> ScheduleRecord:
    item = ScheduleRecord(
        user_id=user_id,
        title=title,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        note=note,
        active=active,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_schedule_by_user_and_id(db: Session, user_id: int, schedule_id: int) -> ScheduleRecord | None:
    return (
        db.query(ScheduleRecord)
        .filter(ScheduleRecord.user_id == user_id, ScheduleRecord.id == schedule_id)
        .first()
    )


def list_schedules_for_user(db: Session, user_id: int, *, active_only: bool = False) -> list[ScheduleRecord]:
    query = db.query(ScheduleRecord).filter(ScheduleRecord.user_id == user_id)
    if active_only:
        query = query.filter(ScheduleRecord.active.is_(True))
    return query.order_by(ScheduleRecord.day_of_week.asc(), ScheduleRecord.start_time.asc()).all()


def update_schedule_record(
    db: Session,
    item: ScheduleRecord,
    *,
    title: str,
    day_of_week: int,
    start_time: str,
    end_time: str,
    note: str | None = None,
    active: bool = True,
) -> ScheduleRecord:
    item.title = title
    item.day_of_week = day_of_week
    item.start_time = start_time
    item.end_time = end_time
    item.note = note
    item.active = active
    db.commit()
    db.refresh(item)
    return item


def delete_schedule_record(db: Session, item: ScheduleRecord) -> None:
    db.delete(item)
    db.commit()


# -- NoteRecord ----------------------------------------------------------------

def create_note_record(
    db: Session,
    *,
    user_id: int,
    title: str,
    content: str = "",
    pinned: bool = False,
) -> "NoteRecord":
    from docops.db.models import NoteRecord
    note = NoteRecord(user_id=user_id, title=title, content=content, pinned=pinned)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def get_note_by_user_and_id(db: Session, user_id: int, note_id: int) -> "NoteRecord | None":
    from docops.db.models import NoteRecord
    return (
        db.query(NoteRecord)
        .filter(NoteRecord.user_id == user_id, NoteRecord.id == note_id)
        .first()
    )


def list_notes_for_user(db: Session, user_id: int) -> "list[NoteRecord]":
    from docops.db.models import NoteRecord
    return (
        db.query(NoteRecord)
        .filter(NoteRecord.user_id == user_id)
        .order_by(NoteRecord.pinned.desc(), NoteRecord.updated_at.desc())
        .all()
    )


def update_note_record(
    db: Session,
    note: "NoteRecord",
    *,
    title: str,
    content: str,
    pinned: bool,
) -> "NoteRecord":
    note.title = title
    note.content = content
    note.pinned = pinned
    db.commit()
    db.refresh(note)
    return note


def delete_note_record(db: Session, note: "NoteRecord") -> None:
    db.delete(note)
    db.commit()


# -- TaskRecord ----------------------------------------------------------------

def create_task_record(
    db: Session,
    *,
    user_id: int,
    title: str,
    note: str | None = None,
    priority: str = "normal",
    due_date: "datetime | None" = None,
) -> "TaskRecord":
    from docops.db.models import TaskRecord
    task = TaskRecord(
        user_id=user_id,
        title=title,
        note=note,
        priority=priority,
        due_date=due_date,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task_by_user_and_id(db: Session, user_id: int, task_id: int) -> "TaskRecord | None":
    from docops.db.models import TaskRecord
    return (
        db.query(TaskRecord)
        .filter(TaskRecord.user_id == user_id, TaskRecord.id == task_id)
        .first()
    )


def list_tasks_for_user(db: Session, user_id: int, *, status: str | None = None) -> "list[TaskRecord]":
    from docops.db.models import TaskRecord
    query = db.query(TaskRecord).filter(TaskRecord.user_id == user_id)
    if status:
        query = query.filter(TaskRecord.status == status)
    return query.order_by(TaskRecord.created_at.desc()).all()


def update_task_record(
    db: Session,
    task: "TaskRecord",
    *,
    title: str,
    note: str | None,
    status: str,
    priority: str,
    due_date: "datetime | None",
) -> "TaskRecord":
    from datetime import datetime, timezone
    task.title = title
    task.note = note
    task.status = status
    task.priority = priority
    task.due_date = due_date
    if status == "done" and task.completed_at is None:
        task.completed_at = datetime.now(timezone.utc)
    elif status != "done":
        task.completed_at = None
    db.commit()
    db.refresh(task)
    return task


def delete_task_record(db: Session, task: "TaskRecord") -> None:
    db.delete(task)
    db.commit()


# -- FlashcardDeck / FlashcardItem --------------------------------------------

def create_flashcard_deck(
    db: Session,
    *,
    user_id: int,
    title: str,
    source_doc: str | None = None,
    cards: list[dict],
) -> "FlashcardDeck":
    from docops.db.models import FlashcardDeck, FlashcardItem

    def _normalize_front(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.casefold().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"[^\w\s]", "", normalized)
        return normalized.strip()

    def _prepare_cards(raw_cards: list[dict]) -> list[dict]:
        prepared: list[dict] = []
        seen_fronts: set[str] = set()
        for card in raw_cards:
            front = str(card.get("front", "")).strip()
            back = str(card.get("back", "")).strip()
            if not front or not back:
                continue

            front_key = _normalize_front(front)
            if not front_key or front_key in seen_fronts:
                continue

            difficulty = str(card.get("difficulty", "media")).strip().casefold()
            if difficulty not in {"facil", "media", "dificil"}:
                difficulty = "media"

            seen_fronts.add(front_key)
            prepared.append({"front": front, "back": back, "difficulty": difficulty})
        return prepared

    safe_cards = _prepare_cards(cards)
    deck = FlashcardDeck(user_id=user_id, title=title, source_doc=source_doc)
    db.add(deck)
    db.flush()
    for c in safe_cards:
        db.add(FlashcardItem(deck_id=deck.id, front=c["front"], back=c["back"], difficulty=c.get("difficulty", "media")))
    db.commit()
    db.refresh(deck)
    return deck


def list_flashcard_decks_for_user(db: Session, user_id: int) -> "list[FlashcardDeck]":
    from docops.db.models import FlashcardDeck
    return (
        db.query(FlashcardDeck)
        .filter(FlashcardDeck.user_id == user_id)
        .order_by(FlashcardDeck.created_at.desc())
        .all()
    )


def get_flashcard_deck_by_user_and_id(db: Session, user_id: int, deck_id: int) -> "FlashcardDeck | None":
    from docops.db.models import FlashcardDeck
    return (
        db.query(FlashcardDeck)
        .filter(FlashcardDeck.user_id == user_id, FlashcardDeck.id == deck_id)
        .first()
    )


def delete_flashcard_deck(db: Session, deck: "FlashcardDeck") -> None:
    db.delete(deck)
    db.commit()


def get_flashcard_item_by_user(db: Session, card_id: int, user_id: int) -> "FlashcardItem | None":
    from docops.db.models import FlashcardItem, FlashcardDeck
    return (
        db.query(FlashcardItem)
        .join(FlashcardDeck, FlashcardItem.deck_id == FlashcardDeck.id)
        .filter(FlashcardItem.id == card_id, FlashcardDeck.user_id == user_id)
        .first()
    )


def update_flashcard_difficulty(db: Session, card_id: int, difficulty: str, user_id: int) -> "FlashcardItem | None":
    from docops.db.models import FlashcardItem, FlashcardDeck
    card = (
        db.query(FlashcardItem)
        .join(FlashcardDeck, FlashcardItem.deck_id == FlashcardDeck.id)
        .filter(FlashcardItem.id == card_id, FlashcardDeck.user_id == user_id)
        .first()
    )
    if not card:
        return None
    card.difficulty = difficulty
    db.commit()
    db.refresh(card)
    return card


# -- TaskChecklistItem --------------------------------------------------------

def list_task_checklist_items(db: Session, task_id: int) -> "list[TaskChecklistItem]":
    from docops.db.models import TaskChecklistItem
    return (
        db.query(TaskChecklistItem)
        .filter(TaskChecklistItem.task_id == task_id)
        .order_by(TaskChecklistItem.position.asc(), TaskChecklistItem.created_at.asc())
        .all()
    )


def create_task_checklist_item(db: Session, *, task_id: int, text: str, position: int = 0) -> "TaskChecklistItem":
    from docops.db.models import TaskChecklistItem
    item = TaskChecklistItem(task_id=task_id, text=text, position=position)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_task_checklist_item(db: Session, item_id: int, task_id: int) -> "TaskChecklistItem | None":
    from docops.db.models import TaskChecklistItem
    return (
        db.query(TaskChecklistItem)
        .filter(TaskChecklistItem.id == item_id, TaskChecklistItem.task_id == task_id)
        .first()
    )


def update_task_checklist_item(
    db: Session,
    item: "TaskChecklistItem",
    *,
    text: str | None = None,
    done: bool | None = None,
) -> "TaskChecklistItem":
    if text is not None:
        item.text = text
    if done is not None:
        item.done = done
    db.commit()
    db.refresh(item)
    return item


def delete_task_checklist_item(db: Session, item: "TaskChecklistItem") -> None:
    db.delete(item)
    db.commit()


# -- TaskActivityLog ----------------------------------------------------------

def list_task_activities(db: Session, task_id: int) -> "list[TaskActivityLog]":
    from docops.db.models import TaskActivityLog
    return (
        db.query(TaskActivityLog)
        .filter(TaskActivityLog.task_id == task_id)
        .order_by(TaskActivityLog.created_at.desc())
        .all()
    )


def create_task_activity(db: Session, *, task_id: int, text: str) -> "TaskActivityLog":
    from docops.db.models import TaskActivityLog
    log = TaskActivityLog(task_id=task_id, text=text)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_task_activity(db: Session, activity_id: int, task_id: int) -> "TaskActivityLog | None":
    from docops.db.models import TaskActivityLog
    return (
        db.query(TaskActivityLog)
        .filter(TaskActivityLog.id == activity_id, TaskActivityLog.task_id == task_id)
        .first()
    )


def delete_task_activity(db: Session, activity: "TaskActivityLog") -> None:
    db.delete(activity)
    db.commit()


# -- StudyPlanRecord ----------------------------------------------------------

def create_study_plan_record(
    db: Session,
    *,
    user_id: int,
    titulo: str,
    doc_name: str,
    plan_text: str,
    tasks_created: int = 0,
    reminders_created: int = 0,
    sessions_count: int = 0,
    deck_id: "int | None" = None,
    hours_per_day: float = 2.0,
    deadline_date: str,
) -> "StudyPlanRecord":
    from docops.db.models import StudyPlanRecord
    record = StudyPlanRecord(
        user_id=user_id,
        titulo=titulo,
        doc_name=doc_name,
        plan_text=plan_text,
        tasks_created=tasks_created,
        reminders_created=reminders_created,
        sessions_count=sessions_count,
        deck_id=deck_id,
        hours_per_day=hours_per_day,
        deadline_date=deadline_date,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_study_plans_for_user(db: Session, user_id: int) -> "list[StudyPlanRecord]":
    from docops.db.models import StudyPlanRecord
    return (
        db.query(StudyPlanRecord)
        .filter(StudyPlanRecord.user_id == user_id)
        .order_by(StudyPlanRecord.created_at.desc())
        .all()
    )


def get_study_plan_by_user_and_id(db: Session, user_id: int, plan_id: int) -> "StudyPlanRecord | None":
    from docops.db.models import StudyPlanRecord
    return (
        db.query(StudyPlanRecord)
        .filter(StudyPlanRecord.user_id == user_id, StudyPlanRecord.id == plan_id)
        .first()
    )


def delete_study_plan_record(db: Session, plan: "StudyPlanRecord") -> None:
    db.delete(plan)
    db.commit()


def update_flashcard_ease(db: Session, card_id: int, ease: int) -> "FlashcardItem | None":
    from docops.db.models import FlashcardItem
    from datetime import datetime, timezone, timedelta
    card = db.get(FlashcardItem, card_id)
    if not card:
        return None
    card.ease = ease
    intervals = {0: 0, 1: 1, 2: 3, 3: 7}
    days = intervals.get(ease, 1)
    card.next_review = datetime.now(timezone.utc) + timedelta(days=days) if days else None
    db.commit()
    db.refresh(card)
    return card


# -- DailyQuestionRecord -------------------------------------------------------

def get_daily_question_for_user(db: Session, user_id: int, date_str: str) -> "DailyQuestionRecord | None":
    from docops.db.models import DailyQuestionRecord
    return db.query(DailyQuestionRecord).filter_by(user_id=user_id, date_generated=date_str).first()


def create_daily_question(
    db: Session,
    *,
    user_id: int,
    question: str,
    answer_hint: str,
    doc_name: str,
    date_generated: str,
) -> "DailyQuestionRecord":
    from docops.db.models import DailyQuestionRecord
    record = DailyQuestionRecord(
        user_id=user_id,
        question=question,
        answer_hint=answer_hint,
        doc_name=doc_name,
        date_generated=date_generated,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# -- ReadingStatusRecord -------------------------------------------------------

def get_reading_status_for_user(db: Session, user_id: int) -> dict[str, str]:
    """Retorna {doc_id: status} para todos os docs com status explícito."""
    from docops.db.models import ReadingStatusRecord
    records = db.query(ReadingStatusRecord).filter_by(user_id=user_id).all()
    return {r.doc_id: r.status for r in records}


def upsert_reading_status(db: Session, user_id: int, doc_id: str, status: str) -> "ReadingStatusRecord":
    from docops.db.models import ReadingStatusRecord
    existing = db.query(ReadingStatusRecord).filter_by(user_id=user_id, doc_id=doc_id).first()
    if existing:
        existing.status = status
        db.commit()
        db.refresh(existing)
        return existing
    record = ReadingStatusRecord(user_id=user_id, doc_id=doc_id, status=status)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
