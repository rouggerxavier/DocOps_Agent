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
