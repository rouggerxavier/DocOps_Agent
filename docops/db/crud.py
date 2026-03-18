"""CRUD helpers for SQL models."""

from __future__ import annotations

from datetime import datetime

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

def create_artifact_record(
    db: Session,
    *,
    user_id: int,
    artifact_type: str,
    filename: str,
    path: str,
    title: str | None = None,
    source_doc_id: str | None = None,
    source_doc_id_2: str | None = None,
) -> ArtifactRecord:
    artifact = ArtifactRecord(
        user_id=user_id,
        artifact_type=artifact_type,
        title=title,
        filename=filename,
        path=path,
        source_doc_id=source_doc_id,
        source_doc_id_2=source_doc_id_2,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def list_artifacts_for_user(db: Session, user_id: int) -> list[ArtifactRecord]:
    return (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.user_id == user_id)
        .order_by(ArtifactRecord.created_at.desc())
        .all()
    )


def get_artifact_by_user_and_filename(db: Session, user_id: int, filename: str) -> ArtifactRecord | None:
    return (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.user_id == user_id, ArtifactRecord.filename == filename)
        .first()
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
    deck = FlashcardDeck(user_id=user_id, title=title, source_doc=source_doc)
    db.add(deck)
    db.flush()
    for c in cards:
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
