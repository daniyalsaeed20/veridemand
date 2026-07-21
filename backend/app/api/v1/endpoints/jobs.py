"""Job listing endpoints (queue positions are computed dynamically)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.api.v1.dependencies import RegistryDep, SettingsDep
from backend.app.contracts.errors import ApiErrorEnvelope, ErrorCode
from backend.app.contracts.jobs import JobListResponse, JobSummary
from backend.app.observability.errors import ApiException
from backend.app.sessions.service import build_session_snapshot

router = APIRouter(tags=["jobs"])

_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorEnvelope, "description": "Session or job not found."}
}


@router.get(
    "/sessions/{session_id}/jobs",
    response_model=JobListResponse,
    summary="List a session's jobs",
    responses=_NOT_FOUND_RESPONSES,
)
async def list_jobs(
    session_id: str,
    registry: RegistryDep,
    settings: SettingsDep,
) -> JobListResponse:
    session = await registry.get(session_id)
    snapshot = build_session_snapshot(session, settings)
    return JobListResponse(jobs=snapshot.jobs)


@router.get(
    "/sessions/{session_id}/jobs/{job_id}",
    response_model=JobSummary,
    summary="Get a single job",
    responses=_NOT_FOUND_RESPONSES,
)
async def get_job(
    session_id: str,
    job_id: str,
    registry: RegistryDep,
    settings: SettingsDep,
) -> JobSummary:
    session = await registry.get(session_id)
    snapshot = build_session_snapshot(session, settings)
    for job in snapshot.jobs:
        if job.job_id == job_id:
            return job
    raise ApiException(
        status_code=404,
        code=ErrorCode.JOB_NOT_FOUND,
        message="Job not found in this session.",
    )
