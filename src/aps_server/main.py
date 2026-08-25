from __future__ import annotations

import hashlib
import hmac
import secrets
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal, TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, Path as APIPath, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from .config import Settings
from .content_models import (
    ContentStatusResponse,
    CreateIdeaRequest,
    CreateIdeaResponse,
    CreateProjectRequest,
    DailyBriefingResponse,
    IdeasResponse,
    ProjectBriefingResponse,
    ProjectCatalogResponse,
    ProjectConfirmationRequired,
    ServiceMaintenanceResponse,
)
from .content_store import ContentStore
from .html_renderer import HTMLRenderer
from .models import CreateJobRequest, Job, JobAccepted, JobStatus, OperationName
from .operations import POLICIES
from .runner import JobRunner
from .store import JobStore
from .vault import VaultRepository


ContentResponse = TypeVar("ContentResponse", bound=BaseModel)


class ContentAPIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = JobStore(settings.data_path)
    content_store = ContentStore(settings.data_path)
    html_renderer = HTMLRenderer()
    vault = VaultRepository(settings.vault_path)
    runner = JobRunner(settings, store, vault)
    bearer = HTTPBearer(auto_error=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        runner.shutdown()

    app = FastAPI(title="APS Content and Automation API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ContentAPIError)
    async def content_api_error(_: Request, error: ContentAPIError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "request_id": "req_" + secrets.token_hex(13).upper(),
                    "details": [],
                }
            },
        )

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
        for token, role in settings.tokens.items():
            if hmac.compare_digest(credentials.credentials, token):
                return role
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    def authenticate_content(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise ContentAPIError(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Bearer token required")
        for token, role in settings.tokens.items():
            if hmac.compare_digest(credentials.credentials, token):
                return role
        raise ContentAPIError(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "Invalid token")

    def content_reader(role: str = Depends(authenticate_content)) -> str:
        if role not in {"operator", "viewer"}:
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Content read is not allowed for this token")
        return role

    def content_owner(role: str = Depends(authenticate_content)) -> str:
        if role != "operator":
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Owner permission is required")
        return role

    def content_format(format: str = Query(default="json")) -> Literal["json", "html"]:
        if format not in {"json", "html"}:
            raise ContentAPIError(status.HTTP_400_BAD_REQUEST, "INVALID_FORMAT", "format must be json or html")
        return format

    def load_content(loader: Callable[[], ContentResponse]) -> ContentResponse:
        try:
            return loader()
        except KeyError as error:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "CONTENT_NOT_GENERATED", "아직 생성된 콘텐츠가 없습니다.") from error
        except (OSError, ValidationError) as error:
            raise ContentAPIError(status.HTTP_500_INTERNAL_SERVER_ERROR, "CONTENT_INVALID", "저장된 콘텐츠가 계약을 통과하지 못했습니다.") from error

    def update_data_checksum(response: ContentResponse) -> ContentResponse:
        data = getattr(response, "data").model_dump_json()
        response.sha256 = hashlib.sha256(data.encode("utf-8")).hexdigest()
        return response

    def html_content(document: str, checksum: str) -> HTMLResponse:
        return HTMLResponse(
            document,
            headers={
                "Cache-Control": "private, max-age=60",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",
                "ETag": f'"{checksum}"',
                "Referrer-Policy": "no-referrer",
                "Vary": "Authorization",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready(_: str = Depends(authenticate)) -> dict[str, object]:
        codex_ready = shutil.which("codex") is not None
        briefing_ready = (settings.vault_path / "scripts" / "daily_briefing.py").is_file()
        if not settings.configured or not codex_ready or not briefing_ready:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"configured": settings.configured, "codex": codex_ready, "briefing_script": briefing_ready},
            )
        return {"status": "ready"}

    @app.get("/v1/operations")
    def list_operations(role: str = Depends(authenticate)) -> dict[str, list[dict[str, object]]]:
        return {
            "operations": [
                {"name": name.value, "write_mode": policy["write_mode"], "enabled": True}
                for name, policy in POLICIES.items()
                if role in policy["roles"]
            ]
        }

    @app.get("/v1/content/briefing/daily", response_model=DailyBriefingResponse)
    def get_daily_briefing(
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> DailyBriefingResponse | HTMLResponse:
        response = load_content(content_store.daily_briefing)
        if format == "html":
            return html_content(html_renderer.daily_briefing(response), response.sha256)
        return response

    @app.get("/v1/content/projects", response_model=ProjectCatalogResponse)
    def get_project_catalog(
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ProjectCatalogResponse | HTMLResponse:
        response = load_content(content_store.project_catalog)
        if format == "html":
            return html_content(html_renderer.project_catalog(response), response.sha256)
        return response

    @app.get("/v1/content/projects/{project_id}/briefing", response_model=ProjectBriefingResponse)
    def get_project_briefing(
        project_id: str = APIPath(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ProjectBriefingResponse | HTMLResponse:
        response = load_content(lambda: content_store.project_briefing(project_id))
        if format == "html":
            return html_content(html_renderer.project_briefing(response), response.sha256)
        return response

    @app.get("/v1/content/services/maintenance", response_model=ServiceMaintenanceResponse)
    def get_service_maintenance(
        scope: Literal["due", "overdue", "upcoming", "all"] = "due",
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ServiceMaintenanceResponse | HTMLResponse:
        response = load_content(content_store.service_maintenance).model_copy(deep=True)
        response.data.scope = scope
        if scope == "due":
            response.data.services = [item for item in response.data.services if item.due_status in {"due", "overdue"}]
        elif scope != "all":
            response.data.services = [item for item in response.data.services if item.due_status == scope]
        response = update_data_checksum(response)
        if format == "html":
            return html_content(html_renderer.service_maintenance(response), response.sha256)
        return response

    @app.get("/v1/content/ideas", response_model=IdeasResponse)
    def get_ideas(
        idea_status: Literal["received", "organized", "proposed", "published", "all"] = Query(default="all", alias="status"),
        cluster_id: str | None = Query(default=None, max_length=80),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> IdeasResponse | HTMLResponse:
        response = load_content(content_store.ideas).model_copy(deep=True)
        if idea_status != "all":
            response.data.ideas = [item for item in response.data.ideas if item.status == idea_status]
        if cluster_id:
            response.data.ideas = [item for item in response.data.ideas if item.cluster_id == cluster_id]
            response.data.clusters = [item for item in response.data.clusters if item.cluster_id == cluster_id]
        response = update_data_checksum(response)
        if format == "html":
            return html_content(html_renderer.ideas(response, idea_status), response.sha256)
        return response

    @app.get("/v1/content/status", response_model=ContentStatusResponse)
    def get_content_status(_: str = Depends(content_reader)) -> ContentStatusResponse:
        return content_store.status()

    @app.post("/v1/ideas", response_model=CreateIdeaResponse, status_code=status.HTTP_201_CREATED)
    def create_idea(request: CreateIdeaRequest, _: str = Depends(content_owner)) -> CreateIdeaResponse:
        return content_store.create_idea(request)

    @app.post("/v1/project-requests", response_model=ProjectConfirmationRequired, status_code=status.HTTP_201_CREATED)
    def create_project_request(
        request: CreateProjectRequest,
        _: str = Depends(content_owner),
    ) -> ProjectConfirmationRequired:
        return content_store.create_project_request(request)

    @app.post("/v1/jobs", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        request: CreateJobRequest,
        role: str = Depends(authenticate),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    ) -> JobAccepted:
        policy = POLICIES[request.operation]
        if role not in policy["roles"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Operation is not allowed for this role")
        if idempotency_key:
            existing = store.find_by_idempotency(role, idempotency_key)
            if existing:
                job = existing.public
                return JobAccepted(
                    job_id=job.job_id,
                    status=job.status,
                    operation=job.operation,
                    created_at=job.created_at,
                    status_url=f"/v1/jobs/{job.job_id}",
                )
        stored = store.create(request, role, datetime.now(UTC), idempotency_key)
        runner.submit(stored.public.job_id)
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
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from error

    @app.post("/v1/jobs/{job_id}/cancel", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
    def cancel_job(job_id: str, role: str = Depends(authenticate)) -> Job:
        if role != "operator":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only operators can cancel jobs")
        try:
            return store.cancel(job_id).public
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from error
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @app.get("/v1/jobs/{job_id}/artifacts/{artifact_id}")
    def get_artifact(job_id: str, artifact_id: str, _: str = Depends(authenticate)) -> FileResponse:
        try:
            stored = store.get(job_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from error
        raw_path = stored.artifact_paths.get(artifact_id)
        if not raw_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
        path = Path(raw_path).resolve()
        artifact_root = (settings.data_path / "artifacts" / job_id).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid artifact path") from error
        if not path.is_file():
            raise HTTPException(status.HTTP_410_GONE, "Artifact expired")
        artifact = next(item for item in stored.public.artifacts if item.artifact_id == artifact_id)
        return FileResponse(path, media_type=artifact.media_type, filename=path.name)

    return app


app = create_app()
