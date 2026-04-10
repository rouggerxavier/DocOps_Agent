"""Ownership validation helpers for multi-tenant authorization.

Provides guard functions that resolve entities and verify ownership,
raising HTTPException(404) on failure to prevent enumeration attacks.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from docops.db.crud import (
    get_document_by_user_and_doc_id,
    get_document_by_user_and_file_name,
    get_artifact_by_user_and_id,
    list_artifacts_by_user_and_filename,
)
from docops.db.models import ArtifactRecord, DocumentRecord


def require_user_document(
    db: Session,
    user_id: int,
    doc_name_or_id: str,
) -> DocumentRecord:
    """Resolve a document by file_name or doc_id and verify ownership.

    Raises 404 if the document does not exist or does not belong to the user.
    """
    doc = get_document_by_user_and_file_name(db, user_id, doc_name_or_id)
    if doc is None:
        doc = get_document_by_user_and_doc_id(db, user_id, doc_name_or_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento nao encontrado.",
        )
    return doc


def require_user_artifact(
    db: Session,
    user_id: int,
    artifact_id_or_name: str | int,
) -> ArtifactRecord:
    """Resolve an artifact by filename or ID and verify ownership.

    Raises 404 if the artifact does not exist or does not belong to the user.
    """
    if isinstance(artifact_id_or_name, int) or str(artifact_id_or_name).isdigit():
        artifact = get_artifact_by_user_and_id(db, user_id, int(artifact_id_or_name))
    else:
        matches = list_artifacts_by_user_and_filename(db, user_id, str(artifact_id_or_name))
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "artifact_filename_ambiguous",
                    "message": "More than one artifact found with this filename. Use artifact_id.",
                    "artifact_ids": [item.id for item in matches],
                },
            )
        artifact = matches[0] if matches else None
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artefato nao encontrado.",
        )
    return artifact
