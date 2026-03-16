"""Job polling route for async summarize/artifact operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from docops.api.schemas import JobStatusResponse
from docops.auth.dependencies import get_current_user
from docops.db.models import User
from docops.services.jobs import get_job

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> JobStatusResponse:
    job = get_job(job_id, user_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job)

