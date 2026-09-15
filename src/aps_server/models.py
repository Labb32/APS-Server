from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OperationName(StrEnum):
    BRIEFING_DAILY = "briefing.daily"
    BRIEFING_PROJECT = "briefing.project"
    VAULT_AUDIT = "vault.audit"
    VAULT_CONTENT_REFRESH = "vault.content.refresh"
    SERVICE_MAINTENANCE_DUE = "service.maintenance_due"
    IDEAS_INDEX_REFRESH = "ideas.index.refresh"
    IDEAS_CURATE = "ideas.curate"


class JobStatus(StrEnum):
    QUEUED = "queued"
    SYNCING = "syncing"
    RUNNING = "running"
    VALIDATING = "validating"
    PUBLISHING = "publishing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ProjectId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


class EmptyJobInput(StrictModel):
    pass


class EmptyJobContext(StrictModel):
    pass


class ProjectBriefingContext(StrictModel):
    project_ids: list[ProjectId] = Field(min_length=1, max_length=1)


class ServiceMaintenanceDueInput(StrictModel):
    date: Date | None = None


class JobRequestModel(StrictModel):
    pass


class BriefingDailyJobRequest(JobRequestModel):
    operation: Literal[OperationName.BRIEFING_DAILY]
    input: EmptyJobInput = Field(default_factory=EmptyJobInput)
    context: EmptyJobContext = Field(default_factory=EmptyJobContext)


class BriefingProjectJobRequest(JobRequestModel):
    operation: Literal[OperationName.BRIEFING_PROJECT]
    input: EmptyJobInput = Field(default_factory=EmptyJobInput)
    context: ProjectBriefingContext


class VaultAuditJobRequest(JobRequestModel):
    operation: Literal[OperationName.VAULT_AUDIT]
    input: EmptyJobInput = Field(default_factory=EmptyJobInput)
    context: EmptyJobContext = Field(default_factory=EmptyJobContext)


class VaultContentRefreshJobRequest(JobRequestModel):
    operation: Literal[OperationName.VAULT_CONTENT_REFRESH] = OperationName.VAULT_CONTENT_REFRESH
    input: EmptyJobInput = Field(default_factory=EmptyJobInput)
    context: EmptyJobContext = Field(default_factory=EmptyJobContext)


class ServiceMaintenanceDueJobRequest(JobRequestModel):
    operation: Literal[OperationName.SERVICE_MAINTENANCE_DUE]
    input: ServiceMaintenanceDueInput = Field(default_factory=ServiceMaintenanceDueInput)
    context: EmptyJobContext = Field(default_factory=EmptyJobContext)


class IdeasIndexRefreshJobRequest(JobRequestModel):
    operation: Literal[OperationName.IDEAS_INDEX_REFRESH]
    input: EmptyJobInput = Field(default_factory=EmptyJobInput)
    context: EmptyJobContext = Field(default_factory=EmptyJobContext)


class IdeasCurateJobRequest(JobRequestModel):
    operation: Literal[OperationName.IDEAS_CURATE]
    input: EmptyJobInput = Field(default_factory=EmptyJobInput)
    context: EmptyJobContext = Field(default_factory=EmptyJobContext)


CreateJobRequest = Annotated[
    BriefingDailyJobRequest
    | BriefingProjectJobRequest
    | VaultAuditJobRequest
    | VaultContentRefreshJobRequest
    | ServiceMaintenanceDueJobRequest
    | IdeasIndexRefreshJobRequest
    | IdeasCurateJobRequest,
    Field(discriminator="operation"),
]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorDetail


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
