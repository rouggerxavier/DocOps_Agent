"""Onboarding tour endpoints.

See `docs/onboarding/spec.md` for the contract.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from docops.api.schemas import (
    OnboardingEventRequest,
    OnboardingEventResponse,
    OnboardingNextHint,
    OnboardingProgress,
    OnboardingSectionView,
    OnboardingStateResponse,
    OnboardingStepView,
    OnboardingTourState,
)
from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User, UserOnboardingStateRecord
from docops.features.flags import is_feature_enabled
from docops.logging import get_logger
from docops.observability import emit_event
from docops.onboarding import (
    ONBOARDING_SCHEMA_VERSION,
    SECTIONS,
    required_step_ids,
    total_step_count,
)

router = APIRouter()
logger = get_logger("docops.api.onboarding")

_ONBOARDING_FLAG = "onboarding_enabled"
_FEATURE_DETAIL = "Onboarding is disabled by feature flag."


def _require_feature() -> None:
    if not is_feature_enabled(_ONBOARDING_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_FEATURE_DETAIL)


def _parse_iso(value: object) -> datetime | None:
    """Tolerate both stringified and naive datetimes in JSON columns."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _build_state_response(record: UserOnboardingStateRecord) -> OnboardingStateResponse:
    completions = record.step_completions or {}
    skips = record.section_skips or {}

    sections: list[OnboardingSectionView] = []
    completed_count = 0
    for section in SECTIONS:
        steps_view: list[OnboardingStepView] = []
        for step in section.steps:
            completed_at = _parse_iso(completions.get(step.id))
            if completed_at is not None:
                completed_count += 1
            next_hint = (
                OnboardingNextHint(section=step.next_hint[0], step=step.next_hint[1])
                if step.next_hint
                else None
            )
            steps_view.append(
                OnboardingStepView(
                    id=step.id,
                    title=step.title,
                    description=step.description,
                    premium=step.premium,
                    completion_mode=step.completion_mode,  # type: ignore[arg-type]
                    completed_at=completed_at,
                    next_hint=next_hint,
                )
            )

        sections.append(
            OnboardingSectionView(
                id=section.id,
                title=section.title,
                icon=section.icon,
                route=section.route,
                skipped=section.id in skips,
                skipped_at=_parse_iso(skips.get(section.id)),
                steps=steps_view,
            )
        )

    required_total = len(required_step_ids(section_skips=skips.keys()))

    tour_state = OnboardingTourState(
        welcome_seen=record.welcome_seen_at is not None,
        started=record.tour_started_at is not None,
        completed=record.tour_completed_at is not None,
        skipped=record.tour_skipped_at is not None,
        progress=OnboardingProgress(
            completed=completed_count,
            total=total_step_count(),
            required_total=required_total,
        ),
    )

    return OnboardingStateResponse(
        schema_version=ONBOARDING_SCHEMA_VERSION,
        schema_upgrade_available=record.schema_version < ONBOARDING_SCHEMA_VERSION,
        tour=tour_state,
        sections=sections,
        last_step_seen=record.last_step_seen,
    )


@router.get("/onboarding/state", response_model=OnboardingStateResponse)
def get_onboarding_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingStateResponse:
    _require_feature()
    record = crud.get_or_create_onboarding_state(db, user_id=current_user.id)
    return _build_state_response(record)


@router.post("/onboarding/events", response_model=OnboardingEventResponse)
def post_onboarding_event(
    body: OnboardingEventRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingEventResponse:
    _require_feature()
    try:
        record, recorded = crud.apply_onboarding_event(
            db,
            user_id=current_user.id,
            event_type=body.event_type,
            step_id=body.step_id,
            section_id=body.section_id,
            metadata=body.metadata,
        )
    except crud.OnboardingValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    emit_event(
        logger,
        "onboarding.event.applied",
        category="onboarding",
        user_id=current_user.id,
        event_type=body.event_type,
        step_id=body.step_id,
        section_id=body.section_id,
        recorded=recorded,
    )

    return OnboardingEventResponse(recorded=recorded, state=_build_state_response(record))


@router.post("/onboarding/reset", response_model=OnboardingStateResponse)
def reset_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingStateResponse:
    _require_feature()
    record = crud.reset_onboarding_state(db, user_id=current_user.id)
    emit_event(
        logger,
        "onboarding.state.reset",
        category="onboarding",
        user_id=current_user.id,
    )
    return _build_state_response(record)
