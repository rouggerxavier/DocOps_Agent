"""Calendar routes: reminders and weekly schedule."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from docops.api.schemas import (
    CalendarOverviewResponse,
    ReminderCreateRequest,
    ReminderItem,
    ReminderUpdateRequest,
    ScheduleCreateRequest,
    ScheduleItem,
    ScheduleUpdateRequest,
)
from docops.auth.dependencies import get_current_user
from docops.db.crud import (
    create_reminder_record,
    create_schedule_record,
    delete_reminder_record,
    delete_schedule_record,
    get_reminder_by_user_and_id,
    get_schedule_by_user_and_id,
    list_reminders_for_user,
    list_schedules_for_user,
    update_reminder_record,
    update_schedule_record,
)
from docops.db.database import get_db
from docops.db.models import User

router = APIRouter(prefix="/calendar")


def _local_tz():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _reminder_item(reminder) -> ReminderItem:
    return ReminderItem(
        id=reminder.id,
        title=reminder.title,
        starts_at=reminder.starts_at,
        ends_at=reminder.ends_at,
        note=reminder.note,
        all_day=bool(reminder.all_day),
    )


def _schedule_item(item) -> ScheduleItem:
    return ScheduleItem(
        id=item.id,
        title=item.title,
        day_of_week=int(item.day_of_week),
        start_time=item.start_time,
        end_time=item.end_time,
        note=item.note,
        active=bool(item.active),
    )


def _validate_time_window(start_time: str, end_time: str) -> None:
    if start_time >= end_time:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")


@router.get("/reminders", response_model=List[ReminderItem])
async def list_reminders(
    start_from: Optional[datetime] = Query(default=None),
    end_to: Optional[datetime] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ReminderItem]:
    reminders = list_reminders_for_user(
        db,
        current_user.id,
        start_from=start_from,
        end_to=end_to,
    )
    return [_reminder_item(r) for r in reminders]


@router.post("/reminders", response_model=ReminderItem)
async def create_reminder(
    body: ReminderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderItem:
    if body.ends_at and body.ends_at < body.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    reminder = create_reminder_record(
        db,
        user_id=current_user.id,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        note=body.note,
        all_day=body.all_day,
    )
    return _reminder_item(reminder)


@router.put("/reminders/{reminder_id}", response_model=ReminderItem)
async def update_reminder(
    reminder_id: int,
    body: ReminderUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderItem:
    reminder = get_reminder_by_user_and_id(db, current_user.id, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if body.ends_at and body.ends_at < body.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    updated = update_reminder_record(
        db,
        reminder,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        note=body.note,
        all_day=body.all_day,
    )
    return _reminder_item(updated)


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    reminder = get_reminder_by_user_and_id(db, current_user.id, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    delete_reminder_record(db, reminder)
    return {"status": "deleted"}


@router.get("/schedules", response_model=List[ScheduleItem])
async def list_schedules(
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ScheduleItem]:
    rows = list_schedules_for_user(db, current_user.id, active_only=active_only)
    return [_schedule_item(row) for row in rows]


@router.post("/schedules", response_model=ScheduleItem)
async def create_schedule(
    body: ScheduleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduleItem:
    _validate_time_window(body.start_time, body.end_time)
    item = create_schedule_record(
        db,
        user_id=current_user.id,
        title=body.title,
        day_of_week=body.day_of_week,
        start_time=body.start_time,
        end_time=body.end_time,
        note=body.note,
        active=body.active,
    )
    return _schedule_item(item)


@router.put("/schedules/{schedule_id}", response_model=ScheduleItem)
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduleItem:
    item = get_schedule_by_user_and_id(db, current_user.id, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    _validate_time_window(body.start_time, body.end_time)
    updated = update_schedule_record(
        db,
        item,
        title=body.title,
        day_of_week=body.day_of_week,
        start_time=body.start_time,
        end_time=body.end_time,
        note=body.note,
        active=body.active,
    )
    return _schedule_item(updated)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    item = get_schedule_by_user_and_id(db, current_user.id, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    delete_schedule_record(db, item)
    return {"status": "deleted"}


@router.get("/overview", response_model=CalendarOverviewResponse)
async def calendar_overview(
    selected_date: Optional[date] = Query(default=None, alias="date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarOverviewResponse:
    tz = _local_tz()
    today = selected_date or datetime.now(tz).date()
    day_start = datetime.combine(today, time.min, tzinfo=tz)
    day_end = datetime.combine(today, time.max, tzinfo=tz)

    reminders = list_reminders_for_user(
        db,
        current_user.id,
        start_from=day_start,
        end_to=day_end,
    )
    schedule = [
        item
        for item in list_schedules_for_user(db, current_user.id, active_only=True)
        if int(item.day_of_week) == int(today.weekday())
    ]
    schedule_sorted = sorted(schedule, key=lambda s: (s.start_time, s.end_time))

    now_local = datetime.now(tz)
    hhmm_now = now_local.strftime("%H:%M")
    current_item = None
    next_item = None
    for item in schedule_sorted:
        if item.start_time <= hhmm_now <= item.end_time and current_item is None:
            current_item = item
            continue
        if hhmm_now < item.start_time and next_item is None:
            next_item = item

    return CalendarOverviewResponse(
        date=today.isoformat(),
        now_iso=now_local.isoformat(),
        today_reminders=[_reminder_item(r) for r in reminders],
        today_schedule=[_schedule_item(s) for s in schedule_sorted],
        current_schedule_item=_schedule_item(current_item) if current_item else None,
        next_schedule_item=_schedule_item(next_item) if next_item else None,
    )

