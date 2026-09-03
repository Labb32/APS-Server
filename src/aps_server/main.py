"""APS Server application assembly and Core job-control endpoints.

Content and Idea routes live in dedicated router modules.  This module keeps
process-owned resources together so the in-process queue and scheduler share a
single, predictable lifecycle.
"""

from __future__ import annotations

import hmac
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agent import build_agent_executor
from .agent.providers import provider_status
from .api_support import ContentAPIError
from .config import Settings
from .content_api import build_content_router
from .content_store import ContentStore
from .extensions import ExtensionListResponse, ExtensionRegistry
from .html_renderer import HTMLRenderer
from .idea_api import build_idea_router
from .idea_service import IdeaService
from .models import CreateJobRequest, ErrorResponse, Job, JobAccepted, JobStatus
from .operations import build_operation_registry
from .runner import JobRunner
from .runtime import OperationRegistryError
from .scheduler import Scheduler, SchedulerStatus
from .store import JobStore
from .vault import VaultRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = JobStore(settings.data_path)
    content_store = ContentStore(settings.data_path)
    html_renderer = HTMLRenderer()
    vault = VaultRepository(settings.vault_path)
    ideas = IdeaService(vault, settings.sync_before_job)
    extensions = ExtensionRegistry(settings.extensions_path)
    agent = build_agent_executor(settings, vault, extensions)
    operations = build_operation_registry(settings, vault, content_store, extensions, agent)
    runner = JobRunner(settings, store, content_store, vault, operations)
    scheduler = Scheduler(settings, store, runner, extensions, operations)
    bearer = HTTPBearer(auto_error=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runner.start()
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown()
            runner.shutdown()

    error_responses = {
        400: {"model": ErrorResponse, "description": "Invalid request format"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Operation forbidden"},
        404: {"model": ErrorResponse, "description": "Resource or materialized content not found"},
        409: {"model": ErrorResponse, "description": "State or idempotency conflict"},
        410: {"model": ErrorResponse, "description": "Artifact expired"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
        500: {"model": ErrorResponse, "description": "Invalid content or internal error"},
        503: {"model": ErrorResponse, "description": "Dependency not ready"},
    }
    app = FastAPI(
        title="APS Content and Automation API",
        version="0.1.0",
        lifespan=lifespan,
        responses=error_responses,
    )
    app.state.agent_executor = agent
    app.state.operation_registry = operations

    def request_id(request: Request) -> str:
        return str(getattr(request.state, "request_id", "req_" + secrets.token_hex(13).upper()))

    def error_response(request: Request, status_code: int, code: str, message: str, details: list[dict[str, object]] | None = None) -> JSONResponse:
        identifier = request_id(request)
        headers = {"X-Request-ID": identifier}
        if status_code == status.HTTP_401_UNAUTHORIZED:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=status_code,
            headers=headers,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": identifier,
                    "details": details or [],
                }
            },
        )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = "req_" + secrets.token_hex(13).upper()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ContentAPIError)
    async def content_api_error(request: Request, error: ContentAPIError) -> JSONResponse:
        return error_response(request, error.status_code, error.code, error.message, error.details)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        details = [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
        return error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "REQUEST_VALIDATION_FAILED",
            "요청이 API 계약을 통과하지 못했습니다.",
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "ROUTE_NOT_FOUND" if error.status_code == status.HTTP_404_NOT_FOUND else "HTTP_ERROR"
        message = "요청한 API 경로를 찾을 수 없습니다." if error.status_code == status.HTTP_404_NOT_FOUND else str(error.detail)
        return error_response(request, error.status_code, code, message)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "요청 처리 중 내부 오류가 발생했습니다.",
        )

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise ContentAPIError(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Bearer token required")
        for token, role in settings.tokens.items():
            if hmac.compare_digest(credentials.credentials, token):
                return role
        raise ContentAPIError(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Invalid token")

    def content_reader(role: str = Depends(authenticate)) -> str:
        if role not in {"operator", "viewer"}:
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Content read is not allowed for this token")
        return role

    app.include_router(build_content_router(content_store, html_renderer, content_reader))
    app.include_router(build_idea_router(content_store, html_renderer, ideas, vault, authenticate, content_reader))

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready(_: str = Depends(authenticate)) -> dict[str, object]:
        briefing_installed = extensions.is_installed("briefing")
        ai_ready, ai_status = provider_status(settings)
        # ExtensionRegistry validates every active manifest and its declared
        # entrypoint/task resources while the application is assembled.
        missing_brief_files: list[str] = []
        briefing_ready = True
        provider_ready = ai_ready
        if not settings.configured or not provider_ready or not briefing_ready:
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "DEPENDENCY_NOT_READY",
                "필수 의존성이 준비되지 않았습니다.",
                [
                    {
                    "configured": settings.configured,
                    "ai": ai_status,
                    "brief_extension": briefing_ready,
                    "briefing_installed": briefing_installed,
                    "missing_brief_files": missing_brief_files,
                    }
                ],
            )
        return {"status": "ready"}

    @app.get("/v1/operations")
    def list_operations(role: str = Depends(authenticate)) -> dict[str, list[dict[str, object]]]:
        return {
            "operations": [
                {
                    "name": spec.name.value,
                    "write_mode": spec.write_mode,
                    "enabled": True,
                }
                for spec in operations.for_role(role)
            ]
        }

    @app.get("/v1/extensions", response_model=ExtensionListResponse)
    def list_extensions(_: str = Depends(authenticate)) -> ExtensionListResponse:
        return ExtensionListResponse(extensions=extensions.active_info())

    @app.get("/v1/scheduler", response_model=SchedulerStatus)
    def get_scheduler_status(role: str = Depends(authenticate)) -> SchedulerStatus:
        if role not in {"operator", "scheduler"}:
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Scheduler status is not allowed for this role")
        return scheduler.status()

    @app.post("/v1/jobs", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        request: CreateJobRequest,
        role: str = Depends(authenticate),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    ) -> JobAccepted:
        try:
            operation = operations.get(request.operation)
        except OperationRegistryError as error:
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error.code,
                "The extension that provides this operation is not installed.",
            ) from error
        if role not in operation.roles:
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Operation is not allowed for this role")
        if idempotency_key:
            existing = store.find_by_idempotency(role, idempotency_key)
            if existing:
                if existing.request != request:
                    raise ContentAPIError(
                        status.HTTP_409_CONFLICT,
                        "IDEMPOTENCY_KEY_REUSED",
                        "동일한 Idempotency-Key가 다른 Job 요청에 이미 사용되었습니다.",
                    )
                job = existing.public
                if job.status == JobStatus.QUEUED:
                    try:
                        runner.submit(job.job_id)
                    except RuntimeError as error:
                        raise ContentAPIError(status.HTTP_503_SERVICE_UNAVAILABLE, "JOB_QUEUE_UNAVAILABLE", str(error)) from error
                return JobAccepted(
                    job_id=job.job_id,
                    status=job.status,
                    operation=job.operation,
                    created_at=job.created_at,
                    status_url=f"/v1/jobs/{job.job_id}",
                )
        stored = store.create(request, role, datetime.now(UTC), idempotency_key)
        try:
            runner.submit(stored.public.job_id)
        except RuntimeError as error:
            store.discard_queued(stored.public.job_id)
            raise ContentAPIError(status.HTTP_503_SERVICE_UNAVAILABLE, "JOB_QUEUE_UNAVAILABLE", str(error)) from error
        job = stored.public
        return JobAccepted(
            job_id=job.job_id,
            status=job.status,
            operation=job.operation,
            created_at=job.created_at,
            status_url=f"/v1/jobs/{job.job_id}",
        )

    @app.get("/v1/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str, _: str = Depends(authenticate)) -> Job:
        try:
            return store.get(job_id).public
        except KeyError as error:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job을 찾을 수 없습니다.") from error

    @app.post("/v1/jobs/{job_id}/cancel", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
    def cancel_job(job_id: str, role: str = Depends(authenticate)) -> Job:
        if role != "operator":
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Only operators can cancel jobs")
        try:
            return store.cancel(job_id).public
        except KeyError as error:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job을 찾을 수 없습니다.") from error
        except ValueError as error:
            raise ContentAPIError(status.HTTP_409_CONFLICT, "JOB_NOT_CANCELLABLE", str(error)) from error

    @app.get("/v1/jobs/{job_id}/artifacts/{artifact_id}")
    def get_artifact(job_id: str, artifact_id: str, _: str = Depends(authenticate)) -> FileResponse:
        try:
            stored = store.get(job_id)
        except KeyError as error:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job을 찾을 수 없습니다.") from error
        raw_path = stored.artifact_paths.get(artifact_id)
        if not raw_path:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "ARTIFACT_NOT_FOUND", "Artifact를 찾을 수 없습니다.")
        path = Path(raw_path).resolve()
        artifact_root = (settings.data_path / "artifacts" / job_id).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError as error:
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "ARTIFACT_PATH_INVALID", "Artifact 경로가 허용 범위를 벗어났습니다.") from error
        if not path.is_file():
            raise ContentAPIError(status.HTTP_410_GONE, "ARTIFACT_EXPIRED", "Artifact가 만료되었거나 제거되었습니다.")
        artifact = next(item for item in stored.public.artifacts if item.artifact_id == artifact_id)
        return FileResponse(path, media_type=artifact.media_type, filename=path.name)

    return app


app = create_app()
