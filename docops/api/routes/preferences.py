"""User preference endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from docops.api.schemas import UserPreferencesResponse, UserPreferencesUpdateRequest
from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.features.flags import require_feature_enabled

router = APIRouter()


def _require_personalization_enabled() -> None:
    require_feature_enabled(
        "personalization_enabled",
        detail="Personalization preferences are disabled by feature flag.",
    )


@router.get("/preferences", response_model=UserPreferencesResponse)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    _require_personalization_enabled()
    payload = crud.get_effective_user_preferences(db, current_user.id)
    return UserPreferencesResponse(**payload)


@router.put("/preferences", response_model=UserPreferencesResponse)
def update_preferences(
    body: UserPreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    _require_personalization_enabled()
    updates = body.model_dump(exclude_unset=True)
    record = crud.update_user_preference_record(
        db,
        user_id=current_user.id,
        default_depth=updates.get("default_depth"),
        tone=updates.get("tone"),
        strictness_preference=updates.get("strictness_preference"),
        schedule_preference=updates.get("schedule_preference"),
    )
    return UserPreferencesResponse(**crud.serialize_user_preferences(record))


@router.post("/preferences/reset", response_model=UserPreferencesResponse)
def reset_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    _require_personalization_enabled()
    record = crud.reset_user_preference_record(db, user_id=current_user.id)
    return UserPreferencesResponse(**crud.serialize_user_preferences(record))

