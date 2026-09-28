"""Job and Scheduler control routes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import FileResponse

from .api_support import ContentAPIError
from .models import CreateJobRequest, Job, JobAccepted, JobStatus, StoredJob
from .runner import JobRunner
from .runtime import OperationRegistry, OperationRegistryError
from .schedule_models import SchedulerStatus
from .scheduler import Scheduler
from .store import JobStore


def build_job_router(
    data_path: Path,
    job_store: JobStore,
    job_runner: JobRunner,
    operation_registry: OperationRegistry,
    scheduler: Scheduler,
    authenticate: Callable[..., str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/scheduler", response_model=SchedulerStatus)
    def get_scheduler_status(role: str = Depends(authenticate)) -> SchedulerStatus:
        if role not in {"operator", "scheduler"}:
            raise ContentAPIError(
                status.HTTP_403_FORBIDDEN,
                "OPERATION_FORBIDDEN",
                "Scheduler status is not allowed for this role",
            )
        return scheduler.status()

    @router.post("/v1/jobs", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        request: CreateJobRequest,
        role: str = Depends(authenticate),
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
        ),
    ) -> JobAccepted:
        try:
            operation = operation_registry.get(request.operation)
        except OperationRegistryError as error:
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error.code,
                "The operation provider is not installed",
            ) from error
        if role not in operation.roles:
            raise ContentAPIError(
                status.HTTP_403_FORBIDDEN,
                "OPERATION_FORBIDDEN",
                "Operation is not allowed for this role",
            )
        availability = operation_registry.availability(operation)
        if not availability.enabled:
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                availability.reason or "OPERATION_NOT_AVAILABLE",
                "Operation is unavailable",
            )
        if idempotency_key:
            existing = job_store.find_by_idempotency(role, idempotency_key)
            if existing is not None:
                if existing.request != request:
                    raise ContentAPIError(
                        status.HTTP_409_CONFLICT,
                        "IDEMPOTENCY_KEY_REUSED",
                        "Idempotency-Key belongs to a different Job request",
                    )
                _resubmit_queued(existing, job_runner)
                return _accepted(existing.public)

        stored = job_store.create(request, role, datetime.now(UTC), idempotency_key)
        try:
            job_runner.submit(stored.public.job_id)
        except RuntimeError as error:
            job_store.discard_queued(stored.public.job_id)
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "JOB_QUEUE_UNAVAILABLE",
                str(error),
            ) from error
        return _accepted(stored.public)

    @router.get("/v1/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str, role: str = Depends(authenticate)) -> Job:
        stored = _stored_job(job_store, job_id)
        _require_job_reader(stored, role)
        return stored.public

    @router.post("/v1/jobs/{job_id}/cancel", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
    def cancel_job(job_id: str, role: str = Depends(authenticate)) -> Job:
        if role != "operator":
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Only operators can cancel Jobs")
        try:
            return job_store.cancel(job_id).public
        except KeyError as error:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job not found") from error
        except ValueError as error:
            raise ContentAPIError(status.HTTP_409_CONFLICT, "JOB_NOT_CANCELLABLE", str(error)) from error

    @router.get("/v1/jobs/{job_id}/artifacts/{artifact_id}")
    def get_artifact(job_id: str, artifact_id: str, role: str = Depends(authenticate)) -> FileResponse:
        stored = _stored_job(job_store, job_id)
        _require_job_reader(stored, role)
        raw_path = stored.artifact_paths.get(artifact_id)
        if raw_path is None:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "ARTIFACT_NOT_FOUND", "Artifact not found")
        path = Path(raw_path).resolve()
        artifact_root = (data_path / "artifacts" / job_id).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError as error:
            raise ContentAPIError(
                status.HTTP_403_FORBIDDEN,
                "ARTIFACT_PATH_INVALID",
                "Artifact path is invalid",
            ) from error
        if not path.is_file():
            raise ContentAPIError(status.HTTP_410_GONE, "ARTIFACT_EXPIRED", "Artifact has expired")
        artifact = next((item for item in stored.public.artifacts if item.artifact_id == artifact_id), None)
        if artifact is None:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "ARTIFACT_NOT_FOUND", "Artifact metadata not found")
        return FileResponse(path, media_type=artifact.media_type, filename=path.name)

    return router


def _stored_job(job_store: JobStore, job_id: str) -> StoredJob:
    try:
        return job_store.get(job_id)
    except KeyError as error:
        raise ContentAPIError(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job not found") from error


def _require_job_reader(stored: StoredJob, role: str) -> None:
    if role != "operator" and stored.role != role:
        raise ContentAPIError(
            status.HTTP_403_FORBIDDEN,
            "OPERATION_FORBIDDEN",
            "Job read is not allowed for this token",
        )


def _resubmit_queued(stored: StoredJob, job_runner: JobRunner) -> None:
    if stored.public.status != JobStatus.QUEUED:
        return
    try:
        job_runner.submit(stored.public.job_id)
    except RuntimeError as error:
        raise ContentAPIError(status.HTTP_503_SERVICE_UNAVAILABLE, "JOB_QUEUE_UNAVAILABLE", str(error)) from error


def _accepted(job: Job) -> JobAccepted:
    return JobAccepted(
        job_id=job.job_id,
        status=job.status,
        operation=job.operation,
        created_at=job.created_at,
        status_url=f"/v1/jobs/{job.job_id}",
    )
