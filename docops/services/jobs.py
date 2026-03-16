"""In-memory async job registry for long-running tasks."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Awaitable, Callable, TypeVar
from uuid import uuid4

JobRunner = Callable[[str], Awaitable[dict[str, Any]]]
T = TypeVar("T")

_LOCK = Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(*, user_id: int, job_type: str, stage: str = "queued") -> dict[str, Any]:
    job_id = uuid4().hex
    now = _utcnow_iso()
    job = {
        "job_id": job_id,
        "user_id": user_id,
        "job_type": job_type,
        "status": "queued",
        "progress": 0,
        "stage": stage,
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK:
        _JOBS[job_id] = job
    return deepcopy(job)


def get_job(job_id: str, *, user_id: int) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or int(job["user_id"]) != int(user_id):
            return None
        return deepcopy(job)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    stage: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        if status is not None:
            job["status"] = status
        if progress is not None:
            job["progress"] = max(0, min(100, int(progress)))
        if stage is not None:
            job["stage"] = stage
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error
        job["updated_at"] = _utcnow_iso()
        return deepcopy(job)


async def run_job(job_id: str, runner: JobRunner) -> None:
    """Execute a coroutine runner and persist status transitions."""
    update_job(job_id, status="running", progress=5, stage="starting")
    try:
        update_job(job_id, progress=25, stage="processing")
        result = await runner(job_id)
        update_job(
            job_id,
            status="succeeded",
            progress=100,
            stage="done",
            result=result,
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            error=str(exc),
        )


def schedule_job(job_id: str, runner: JobRunner) -> None:
    """Create a detached task that updates this job in the background."""
    asyncio.create_task(run_job(job_id, runner))


async def run_thread_with_progress(
    *,
    job_id: str,
    fn: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any] | None = None,
    stage: str = "processing",
    start_progress: int = 30,
    max_progress: int = 80,
    step: int = 4,
    interval_seconds: float = 2.0,
) -> T:
    """
    Run a blocking callable in a worker thread while emitting heartbeat progress.

    This avoids long periods where the UI appears frozen at a single percentage.
    """
    local_kwargs = kwargs or {}
    update_job(job_id, progress=start_progress, stage=stage)

    task = asyncio.create_task(asyncio.to_thread(fn, *args, **local_kwargs))
    progress = int(start_progress)

    while not task.done():
        await asyncio.sleep(interval_seconds)
        if task.done():
            break
        progress = min(int(max_progress), progress + int(step))
        update_job(job_id, progress=progress, stage=stage)

    return await task
