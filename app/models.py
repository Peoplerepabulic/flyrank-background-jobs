"""Pydantic schemas for the reports API."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class ReportRequest(BaseModel):
    """POST /reports request body."""

    title: str = Field(min_length=1, max_length=200)
    sections: list[str] = Field(default_factory=list)


class ReportAccepted(BaseModel):
    """POST /reports response body (202 for a new job)."""

    job_id: str
    status: JobStatus


class JobResponse(BaseModel):
    """GET /reports/{job_id} response body."""

    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    result: Optional[dict[str, Any]] = None
