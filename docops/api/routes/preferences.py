"""User preference endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from docops.api.schemas import UserPreferencesResponse, UserPreferencesUpdateRequest
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.features.flags import require_feature_enabled
from docops.logging import get_logger
from docops.observability import emit_event

router = APIRouter()
logger = get_logger("docops.api.preferences")
_PREFERENCE_FIELDS = (
    "default_depth",
    "tone",
    "strictness_preference",
    "schedule_preference",
)


def _require_personalization_enabled() -> None:
    require_feature_enabled(
        "personalization_enabled",
        detail="Personalization preferences are disabled by feature flag.",
    )


def _apply_retention_and_audit(db: Session, user_id: int) -> bool:
    purged = crud.apply_user_preference_retention_policy(db, user_id=user_id)
    if purged:
        emit_event(
            logger,
            "preferences.retention.purged",
            category="personalization",
            user_id=user_id,
            retention_days=config.preferences_retention_days,
            policy="updated_at_window",
        )
    return purged


@router.get("/preferences", response_model=UserPreferencesResponse)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    _require_personalization_enabled()
    _apply_retention_and_audit(db, current_user.id)
    payload = crud.get_effective_user_preferences(db, current_user.id)
    return UserPreferencesResponse(**payload)


@router.put("/preferences", response_model=UserPreferencesResponse)
def update_preferences(
    body: UserPreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    _require_personalization_enabled()
    retention_purged = _apply_retention_and_audit(db, current_user.id)
    previous = crud.get_effective_user_preferences(db, current_user.id)
    updates = body.model_dump(exclude_unset=True)
    record = crud.update_user_preference_record(
        db,
        user_id=current_user.id,
        default_depth=updates.get("default_depth"),
        tone=updates.get("tone"),
        strictness_preference=updates.get("strictness_preference"),
        schedule_preference=updates.get("schedule_preference"),
    )
    serialized = crud.serialize_user_preferences(record)
    changed_fields = [field for field in _PREFERENCE_FIELDS if previous.get(field) != serialized.get(field)]
    emit_event(
        logger,
        "preferences.audit.updated",
        category="personalization",
        user_id=current_user.id,
        changed_fields=changed_fields,
        requested_fields=sorted(updates.keys()),
        retention_purged=retention_purged,
    )
    return UserPreferencesResponse(**serialized)


@router.post("/preferences/reset", response_model=UserPreferencesResponse)
def reset_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    _require_personalization_enabled()
    retention_purged = _apply_retention_and_audit(db, current_user.id)
    previous = crud.get_effective_user_preferences(db, current_user.id)
    record = crud.reset_user_preference_record(db, user_id=current_user.id)
    serialized = crud.serialize_user_preferences(record)
    changed_fields = [field for field in _PREFERENCE_FIELDS if previous.get(field) != serialized.get(field)]
    emit_event(
        logger,
        "preferences.audit.reset",
        category="personalization",
        user_id=current_user.id,
        changed_fields=changed_fields,
        retention_purged=retention_purged,
    )
    return UserPreferencesResponse(**serialized)


@router.delete("/preferences", status_code=status.HTTP_204_NO_CONTENT)
def delete_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _require_personalization_enabled()
    retention_purged = _apply_retention_and_audit(db, current_user.id)
    deleted = crud.delete_user_preference_record(db, user_id=current_user.id)
    emit_event(
        logger,
        "preferences.audit.deleted",
        category="personalization",
        user_id=current_user.id,
        record_deleted=deleted,
        retention_purged=retention_purged,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
