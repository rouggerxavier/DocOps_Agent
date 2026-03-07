"""Operações CRUD — User, DocumentRecord, ArtifactRecord."""

from __future__ import annotations

from sqlalchemy.orm import Session

from docops.db.models import ArtifactRecord, DocumentRecord, User


# ── User ──────────────────────────────────────────────────────────────────────

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


# ── DocumentRecord ────────────────────────────────────────────────────────────

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


# ── ArtifactRecord ────────────────────────────────────────────────────────────

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
