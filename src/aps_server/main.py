from __future__ import annotations

import hmac
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings
from .models import CreateJobRequest, Job, JobAccepted, JobStatus, OperationName
from .operations import POLICIES
from .runner import JobRunner
from .store import JobStore
from .vault import VaultRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = JobStore(settings.data_path)
    vault = VaultRepository(settings.vault_path)
    runner = JobRunner(settings, store, vault)
    bearer = HTTPBearer(auto_error=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        runner.shutdown()

    app = FastAPI(title="APS Automation and Agent API", version="0.1.0", lifespan=lifespan)

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
        for token, role in settings.tokens.items():
            if hmac.compare_digest(credentials.credentials, token):
                return role
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

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
