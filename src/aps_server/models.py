from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OperationName(StrEnum):
    BRIEFING_DAILY = "briefing.daily"
    BRIEFING_PROJECT = "briefing.project"
    VAULT_AUDIT = "vault.audit"
    SERVICE_MAINTENANCE_DUE = "service.maintenance_due"


class JobStatus(StrEnum):
    QUEUED = "queued"
    SYNCING = "syncing"
    RUNNING = "running"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_ids: list[str] = Field(default_factory=list, max_length=20)
    include_services: bool = True

    @field_validator("project_ids")
    @classmethod
    def validate_project_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or len(value) > 64 or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in value):
                raise ValueError(f"invalid project id: {value}")
        return list(dict.fromkeys(values))

class CreateJobRequest(BaseModel):
    operation: OperationName
    input: dict[str, Any] = Field(default_factory=dict)
    context: JobContext = Field(default_factory=JobContext)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class Artifact(BaseModel):
    artifact_id: str
    media_type: str
    download_url: str
    sha256: str
    expires_at: datetime | None = None


class Job(BaseModel):
    job_id: str
    status: JobStatus
    operation: OperationName
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    vault_commit: str | None = None
    result: dict[str, Any] | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    error: ErrorDetail | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    operation: OperationName
    created_at: datetime
    status_url: str


class StoredJob(BaseModel):
    public: Job
    request: CreateJobRequest
    role: str
    idempotency_key: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
