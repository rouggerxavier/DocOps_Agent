"""Premium conversion and value analytics routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.observability import emit_event, get_request_correlation_id

logger = get_logger("docops.api.analytics")
router = APIRouter()

PremiumEventType = Literal[
    "premium_touchpoint_viewed",
    "upgrade_initiated",
    "upgrade_completed",
    "premium_feature_activation",
]

_PREMIUM_EVENT_ORDER: tuple[PremiumEventType, ...] = (
    "premium_touchpoint_viewed",
    "upgrade_initiated",
    "upgrade_completed",
    "premium_feature_activation",
)


class PremiumAnalyticsTrackRequest(BaseModel):
    event_type: PremiumEventType
    touchpoint: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    capability: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PremiumAnalyticsTrackResponse(BaseModel):
    status: str = "recorded"
    id: int
    event_type: PremiumEventType
    touchpoint: str
    capability: str | None = None
    created_at: datetime


class PremiumFunnelStageStats(BaseModel):
    events: int = 0
    users: int = 0


class PremiumFunnelConversion(BaseModel):
    view_to_upgrade_initiated: float | None = None
    initiated_to_completed: float | None = None
    completed_to_activation: float | None = None
    view_to_activation: float | None = None


class PremiumTouchpointFunnel(BaseModel):
    touchpoint: str
    capability: str | None = None
    stages: dict[str, PremiumFunnelStageStats]
    conversion: PremiumFunnelConversion


class PremiumFunnelResponse(BaseModel):
    window_days: int
    generated_at: datetime
    totals: dict[str, int]
    touchpoints: list[PremiumTouchpointFunnel]


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


@router.post("/analytics/premium/events", response_model=PremiumAnalyticsTrackResponse)
async def track_premium_event(
    payload: PremiumAnalyticsTrackRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = crud.create_premium_analytics_event(
        db,
        user_id=current_user.id,
        event_type=payload.event_type,
        touchpoint=payload.touchpoint,
        capability=payload.capability,
        correlation_id=get_request_correlation_id(request),
        metadata=dict(payload.metadata or {}),
    )

    emit_event(
        logger,
        "premium.analytics.event_recorded",
        category="premium_analytics",
        user_id=current_user.id,
        event_type=payload.event_type,
        touchpoint=payload.touchpoint,
        capability=payload.capability,
        event_record_id=record.id,
    )

    return PremiumAnalyticsTrackResponse(
        id=record.id,
        event_type=payload.event_type,
        touchpoint=record.touchpoint,
        capability=record.capability,
        created_at=record.created_at,
    )


@router.get("/analytics/premium/funnel", response_model=PremiumFunnelResponse)
async def get_premium_funnel(
    window_days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user  # authenticated access; aggregate is workspace-level analytics.
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=window_days)
    rows = crud.list_premium_analytics_events_since(db, since=since)

    by_touchpoint: dict[str, dict[str, Any]] = {}
    total_users: set[int] = set()

    for row in rows:
        if row.event_type not in _PREMIUM_EVENT_ORDER:
            continue
        total_users.add(int(row.user_id))

        current = by_touchpoint.setdefault(
            row.touchpoint,
            {
                "touchpoint": row.touchpoint,
                "capability": None,
                "stages": {
                    event_type: {"events": 0, "users": set()}
                    for event_type in _PREMIUM_EVENT_ORDER
                },
            },
        )
        if not current["capability"] and row.capability:
            current["capability"] = row.capability

        stage = current["stages"][row.event_type]
        stage["events"] += 1
        stage["users"].add(int(row.user_id))

    touchpoint_items: list[PremiumTouchpointFunnel] = []
    total_events = 0

    for value in by_touchpoint.values():
        stages_payload: dict[str, PremiumFunnelStageStats] = {}
        stage_user_counts: dict[str, int] = {}

        for event_type in _PREMIUM_EVENT_ORDER:
            stage_info = value["stages"][event_type]
            users_count = len(stage_info["users"])
            events_count = int(stage_info["events"])
            total_events += events_count
            stage_user_counts[event_type] = users_count
            stages_payload[event_type] = PremiumFunnelStageStats(
                events=events_count,
                users=users_count,
            )

        touchpoint_items.append(
            PremiumTouchpointFunnel(
                touchpoint=value["touchpoint"],
                capability=value["capability"],
                stages=stages_payload,
                conversion=PremiumFunnelConversion(
                    view_to_upgrade_initiated=_safe_ratio(
                        stage_user_counts["upgrade_initiated"],
                        stage_user_counts["premium_touchpoint_viewed"],
                    ),
                    initiated_to_completed=_safe_ratio(
                        stage_user_counts["upgrade_completed"],
                        stage_user_counts["upgrade_initiated"],
                    ),
                    completed_to_activation=_safe_ratio(
                        stage_user_counts["premium_feature_activation"],
                        stage_user_counts["upgrade_completed"],
                    ),
                    view_to_activation=_safe_ratio(
                        stage_user_counts["premium_feature_activation"],
                        stage_user_counts["premium_touchpoint_viewed"],
                    ),
                ),
            )
        )

    touchpoint_items.sort(
        key=lambda item: (
            item.stages["premium_touchpoint_viewed"].users,
            item.stages["premium_feature_activation"].users,
            item.touchpoint,
        ),
        reverse=True,
    )

    emit_event(
        logger,
        "premium.analytics.funnel_requested",
        category="premium_analytics",
        window_days=window_days,
        touchpoint_count=len(touchpoint_items),
        event_count=total_events,
        user_count=len(total_users),
    )

    return PremiumFunnelResponse(
        window_days=window_days,
        generated_at=now_utc,
        totals={
            "events": total_events,
            "users": len(total_users),
            "touchpoints": len(touchpoint_items),
        },
        touchpoints=touchpoint_items,
    )
