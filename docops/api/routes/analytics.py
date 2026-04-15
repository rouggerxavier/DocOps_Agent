"""Premium conversion and value analytics routes."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user, require_admin_user
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

RecommendationAction = Literal[
    "dismiss",
    "snooze",
    "mute_category",
    "feedback_useful",
    "feedback_not_useful",
]
_RECOMMENDATION_ACTION_ORDER: tuple[RecommendationAction, ...] = (
    "dismiss",
    "snooze",
    "mute_category",
    "feedback_useful",
    "feedback_not_useful",
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


class PremiumFunnelOverall(BaseModel):
    viewed_users: int = 0
    upgrade_initiated_users: int = 0
    upgrade_completed_users: int = 0
    activated_users: int = 0
    conversion: PremiumFunnelConversion


class PremiumFunnelResponse(BaseModel):
    window_days: int
    generated_at: datetime
    totals: dict[str, int]
    overall: PremiumFunnelOverall
    touchpoints: list[PremiumTouchpointFunnel]


class RecommendationActionBreakdown(BaseModel):
    dismiss: int = 0
    snooze: int = 0
    mute_category: int = 0
    feedback_useful: int = 0
    feedback_not_useful: int = 0
    total: int = 0
    feedback_useful_rate: float | None = None


class RecommendationCategoryAnalyticsItem(BaseModel):
    category: str
    actions: RecommendationActionBreakdown
    users: int = 0
    recommendations: int = 0


class RecommendationTouchpointAnalyticsItem(BaseModel):
    touchpoint: str
    actions: RecommendationActionBreakdown
    users: int = 0
    recommendations: int = 0


class RecommendationAnalyticsTotals(BaseModel):
    events: int = 0
    users: int = 0
    categories: int = 0
    touchpoints: int = 0
    recommendations: int = 0


class PremiumRecommendationAnalyticsResponse(BaseModel):
    window_days: int
    generated_at: datetime
    totals: RecommendationAnalyticsTotals
    actions: RecommendationActionBreakdown
    categories: list[RecommendationCategoryAnalyticsItem]
    touchpoints: list[RecommendationTouchpointAnalyticsItem]


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _parse_metadata_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _resolve_recommendation_action(event_type: str, metadata: dict[str, Any]) -> RecommendationAction | None:
    normalized_type = str(event_type or "").strip().lower()
    if normalized_type == "recommendation.dismissed":
        return "dismiss"
    if normalized_type == "recommendation.snoozed":
        return "snooze"
    if normalized_type == "recommendation.category_muted":
        return "mute_category"
    if normalized_type == "recommendation.feedback.recorded":
        metadata_action = str(metadata.get("action") or "").strip().lower()
        if metadata_action in _RECOMMENDATION_ACTION_ORDER:
            return metadata_action  # type: ignore[return-value]
        useful = metadata.get("useful")
        if useful is True:
            return "feedback_useful"
        if useful is False:
            return "feedback_not_useful"
    return None


def _build_recommendation_action_breakdown(action_counts: dict[str, int]) -> RecommendationActionBreakdown:
    feedback_useful = int(action_counts.get("feedback_useful", 0))
    feedback_not_useful = int(action_counts.get("feedback_not_useful", 0))
    feedback_total = feedback_useful + feedback_not_useful
    total = sum(int(action_counts.get(action, 0)) for action in _RECOMMENDATION_ACTION_ORDER)
    return RecommendationActionBreakdown(
        dismiss=int(action_counts.get("dismiss", 0)),
        snooze=int(action_counts.get("snooze", 0)),
        mute_category=int(action_counts.get("mute_category", 0)),
        feedback_useful=feedback_useful,
        feedback_not_useful=feedback_not_useful,
        total=total,
        feedback_useful_rate=_safe_ratio(feedback_useful, feedback_total),
    )


def _format_csv_rate(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.4f}"


def _csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_funnel_response(
    rows: list[Any],
    *,
    window_days: int,
    generated_at: datetime,
) -> PremiumFunnelResponse:
    by_touchpoint: dict[str, dict[str, Any]] = {}
    total_users: set[int] = set()
    overall_stage_users: dict[str, set[int]] = {event_type: set() for event_type in _PREMIUM_EVENT_ORDER}
    total_events = 0

    for row in rows:
        if row.event_type not in _PREMIUM_EVENT_ORDER:
            continue
        user_id = int(row.user_id)
        total_users.add(user_id)
        overall_stage_users[row.event_type].add(user_id)
        total_events += 1

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
        stage["users"].add(user_id)

    touchpoint_items: list[PremiumTouchpointFunnel] = []
    for value in by_touchpoint.values():
        stages_payload: dict[str, PremiumFunnelStageStats] = {}
        stage_user_counts: dict[str, int] = {}

        for event_type in _PREMIUM_EVENT_ORDER:
            stage_info = value["stages"][event_type]
            users_count = len(stage_info["users"])
            events_count = int(stage_info["events"])
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

    overall_viewed = len(overall_stage_users["premium_touchpoint_viewed"])
    overall_initiated = len(overall_stage_users["upgrade_initiated"])
    overall_completed = len(overall_stage_users["upgrade_completed"])
    overall_activated = len(overall_stage_users["premium_feature_activation"])

    return PremiumFunnelResponse(
        window_days=window_days,
        generated_at=generated_at,
        totals={
            "events": total_events,
            "users": len(total_users),
            "touchpoints": len(touchpoint_items),
        },
        overall=PremiumFunnelOverall(
            viewed_users=overall_viewed,
            upgrade_initiated_users=overall_initiated,
            upgrade_completed_users=overall_completed,
            activated_users=overall_activated,
            conversion=PremiumFunnelConversion(
                view_to_upgrade_initiated=_safe_ratio(overall_initiated, overall_viewed),
                initiated_to_completed=_safe_ratio(overall_completed, overall_initiated),
                completed_to_activation=_safe_ratio(overall_activated, overall_completed),
                view_to_activation=_safe_ratio(overall_activated, overall_viewed),
            ),
        ),
        touchpoints=touchpoint_items,
    )


def _build_funnel_csv(response: PremiumFunnelResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "window_days",
            "generated_at",
            "scope",
            "touchpoint",
            "capability",
            "events_total",
            "users_total",
            "view_users",
            "view_events",
            "upgrade_initiated_users",
            "upgrade_initiated_events",
            "upgrade_completed_users",
            "upgrade_completed_events",
            "activation_users",
            "activation_events",
            "view_to_upgrade_initiated",
            "initiated_to_completed",
            "completed_to_activation",
            "view_to_activation",
        ]
    )
    writer.writerow(
        [
            response.window_days,
            response.generated_at.isoformat(),
            "overall",
            "all",
            "",
            response.totals.get("events", 0),
            response.totals.get("users", 0),
            response.overall.viewed_users,
            "",
            response.overall.upgrade_initiated_users,
            "",
            response.overall.upgrade_completed_users,
            "",
            response.overall.activated_users,
            "",
            _format_csv_rate(response.overall.conversion.view_to_upgrade_initiated),
            _format_csv_rate(response.overall.conversion.initiated_to_completed),
            _format_csv_rate(response.overall.conversion.completed_to_activation),
            _format_csv_rate(response.overall.conversion.view_to_activation),
        ]
    )

    for item in response.touchpoints:
        stage_view = item.stages["premium_touchpoint_viewed"]
        stage_initiated = item.stages["upgrade_initiated"]
        stage_completed = item.stages["upgrade_completed"]
        stage_activation = item.stages["premium_feature_activation"]
        writer.writerow(
            [
                response.window_days,
                response.generated_at.isoformat(),
                "touchpoint",
                item.touchpoint,
                item.capability or "",
                (
                    stage_view.events
                    + stage_initiated.events
                    + stage_completed.events
                    + stage_activation.events
                ),
                stage_view.users,
                stage_view.users,
                stage_view.events,
                stage_initiated.users,
                stage_initiated.events,
                stage_completed.users,
                stage_completed.events,
                stage_activation.users,
                stage_activation.events,
                _format_csv_rate(item.conversion.view_to_upgrade_initiated),
                _format_csv_rate(item.conversion.initiated_to_completed),
                _format_csv_rate(item.conversion.completed_to_activation),
                _format_csv_rate(item.conversion.view_to_activation),
            ]
        )
    return buffer.getvalue()


def _build_recommendation_analytics_response(
    rows: list[Any],
    *,
    window_days: int,
    generated_at: datetime,
) -> PremiumRecommendationAnalyticsResponse:
    action_counts: dict[str, int] = {action: 0 for action in _RECOMMENDATION_ACTION_ORDER}
    unique_users: set[int] = set()
    recommendation_ids: set[str] = set()

    by_category: dict[str, dict[str, Any]] = {}
    by_touchpoint: dict[str, dict[str, Any]] = {}

    total_events = 0
    for row in rows:
        event_type = str(row.event_type or "").strip().lower()
        if not event_type.startswith("recommendation."):
            continue
        metadata = _parse_metadata_json(row.metadata_json)
        action = _resolve_recommendation_action(event_type, metadata)
        if action is None:
            continue
        total_events += 1

        category = str(metadata.get("category") or "").strip().lower() or "uncategorized"
        touchpoint = str(row.touchpoint or "").strip().lower() or "unknown"
        recommendation_id = str(metadata.get("recommendation_id") or "").strip().lower()
        user_id = int(row.user_id)

        unique_users.add(user_id)
        action_counts[action] = int(action_counts.get(action, 0)) + 1
        if recommendation_id:
            recommendation_ids.add(recommendation_id)

        category_entry = by_category.setdefault(
            category,
            {
                "action_counts": {item: 0 for item in _RECOMMENDATION_ACTION_ORDER},
                "users": set(),
                "recommendation_ids": set(),
            },
        )
        category_entry["action_counts"][action] += 1
        category_entry["users"].add(user_id)
        if recommendation_id:
            category_entry["recommendation_ids"].add(recommendation_id)

        touchpoint_entry = by_touchpoint.setdefault(
            touchpoint,
            {
                "action_counts": {item: 0 for item in _RECOMMENDATION_ACTION_ORDER},
                "users": set(),
                "recommendation_ids": set(),
            },
        )
        touchpoint_entry["action_counts"][action] += 1
        touchpoint_entry["users"].add(user_id)
        if recommendation_id:
            touchpoint_entry["recommendation_ids"].add(recommendation_id)

    categories = [
        RecommendationCategoryAnalyticsItem(
            category=category,
            actions=_build_recommendation_action_breakdown(data["action_counts"]),
            users=len(data["users"]),
            recommendations=len(data["recommendation_ids"]),
        )
        for category, data in by_category.items()
    ]
    categories.sort(key=lambda item: (item.actions.total, item.users, item.category), reverse=True)

    touchpoints = [
        RecommendationTouchpointAnalyticsItem(
            touchpoint=touchpoint,
            actions=_build_recommendation_action_breakdown(data["action_counts"]),
            users=len(data["users"]),
            recommendations=len(data["recommendation_ids"]),
        )
        for touchpoint, data in by_touchpoint.items()
    ]
    touchpoints.sort(key=lambda item: (item.actions.total, item.users, item.touchpoint), reverse=True)

    return PremiumRecommendationAnalyticsResponse(
        window_days=window_days,
        generated_at=generated_at,
        totals=RecommendationAnalyticsTotals(
            events=total_events,
            users=len(unique_users),
            categories=len(categories),
            touchpoints=len(touchpoints),
            recommendations=len(recommendation_ids),
        ),
        actions=_build_recommendation_action_breakdown(action_counts),
        categories=categories,
        touchpoints=touchpoints,
    )


def _build_recommendation_analytics_csv(response: PremiumRecommendationAnalyticsResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "window_days",
            "generated_at",
            "scope",
            "key",
            "users",
            "recommendations",
            "actions_total",
            "dismiss",
            "snooze",
            "mute_category",
            "feedback_useful",
            "feedback_not_useful",
            "feedback_useful_rate",
        ]
    )
    writer.writerow(
        [
            response.window_days,
            response.generated_at.isoformat(),
            "overall",
            "all",
            response.totals.users,
            response.totals.recommendations,
            response.actions.total,
            response.actions.dismiss,
            response.actions.snooze,
            response.actions.mute_category,
            response.actions.feedback_useful,
            response.actions.feedback_not_useful,
            _format_csv_rate(response.actions.feedback_useful_rate),
        ]
    )
    for category in response.categories:
        writer.writerow(
            [
                response.window_days,
                response.generated_at.isoformat(),
                "category",
                category.category,
                category.users,
                category.recommendations,
                category.actions.total,
                category.actions.dismiss,
                category.actions.snooze,
                category.actions.mute_category,
                category.actions.feedback_useful,
                category.actions.feedback_not_useful,
                _format_csv_rate(category.actions.feedback_useful_rate),
            ]
        )
    for touchpoint in response.touchpoints:
        writer.writerow(
            [
                response.window_days,
                response.generated_at.isoformat(),
                "touchpoint",
                touchpoint.touchpoint,
                touchpoint.users,
                touchpoint.recommendations,
                touchpoint.actions.total,
                touchpoint.actions.dismiss,
                touchpoint.actions.snooze,
                touchpoint.actions.mute_category,
                touchpoint.actions.feedback_useful,
                touchpoint.actions.feedback_not_useful,
                _format_csv_rate(touchpoint.actions.feedback_useful_rate),
            ]
        )
    return buffer.getvalue()


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
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    _ = current_user  # authenticated access; aggregate is workspace-level analytics.
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=window_days)
    rows = crud.list_premium_analytics_events_since(db, since=since)
    payload = _build_funnel_response(rows, window_days=window_days, generated_at=now_utc)

    emit_event(
        logger,
        "premium.analytics.funnel_requested",
        category="premium_analytics",
        window_days=window_days,
        touchpoint_count=payload.totals.get("touchpoints", 0),
        event_count=payload.totals.get("events", 0),
        user_count=payload.totals.get("users", 0),
    )

    return payload


@router.get("/analytics/premium/recommendations", response_model=PremiumRecommendationAnalyticsResponse)
async def get_premium_recommendation_analytics(
    window_days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    _ = current_user  # authenticated access; aggregate is workspace-level analytics.
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=window_days)
    rows = crud.list_premium_analytics_events_since(db, since=since)
    payload = _build_recommendation_analytics_response(
        rows,
        window_days=window_days,
        generated_at=now_utc,
    )

    emit_event(
        logger,
        "premium.analytics.recommendations_requested",
        category="premium_analytics",
        window_days=window_days,
        event_count=payload.totals.events,
        user_count=payload.totals.users,
        category_count=payload.totals.categories,
        touchpoint_count=payload.totals.touchpoints,
    )

    return payload


@router.get("/analytics/premium/funnel/export.csv")
async def export_premium_funnel_csv(
    window_days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    _ = current_user  # authenticated access; aggregate is workspace-level analytics.
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=window_days)
    rows = crud.list_premium_analytics_events_since(db, since=since)
    payload = _build_funnel_response(rows, window_days=window_days, generated_at=now_utc)
    content = _build_funnel_csv(payload)

    emit_event(
        logger,
        "premium.analytics.funnel_export_requested",
        category="premium_analytics",
        window_days=window_days,
        touchpoint_count=payload.totals.get("touchpoints", 0),
        event_count=payload.totals.get("events", 0),
        user_count=payload.totals.get("users", 0),
    )

    filename = f"premium_funnel_{window_days}d_{now_utc.strftime('%Y%m%d_%H%M%S')}.csv"
    return _csv_response(content, filename)


@router.get("/analytics/premium/recommendations/export.csv")
async def export_premium_recommendations_csv(
    window_days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    _ = current_user  # authenticated access; aggregate is workspace-level analytics.
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=window_days)
    rows = crud.list_premium_analytics_events_since(db, since=since)
    payload = _build_recommendation_analytics_response(
        rows,
        window_days=window_days,
        generated_at=now_utc,
    )
    content = _build_recommendation_analytics_csv(payload)

    emit_event(
        logger,
        "premium.analytics.recommendations_export_requested",
        category="premium_analytics",
        window_days=window_days,
        event_count=payload.totals.events,
        user_count=payload.totals.users,
        category_count=payload.totals.categories,
        touchpoint_count=payload.totals.touchpoints,
    )

    filename = f"premium_recommendations_{window_days}d_{now_utc.strftime('%Y%m%d_%H%M%S')}.csv"
    return _csv_response(content, filename)
