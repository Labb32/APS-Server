"""APS Server application assembly."""

from __future__ import annotations

import hmac
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .agent import build_agent_executor
from .agent.providers import provider_status
from .api_support import ContentAPIError
from .config import Settings
from .content_api import build_content_router
from .content_store import ContentStore
from .document_search import DocumentSearchIndex
from .extensions import ExtensionListResponse, ExtensionRegistry
from .html_renderer import HTMLRenderer
from .idea_api import build_idea_router
from .idea_service import IdeaService
from .job_api import build_job_router
from .models import ErrorResponse
from .migration_api import build_migration_router
from .operations import build_operation_registry
from .runner import JobRunner
from .scheduler import Scheduler
from .search_api import build_search_router
from .store import JobStore
from .vault import VaultRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    job_store = JobStore(settings.data_path)
    content_store = ContentStore(settings.data_path)
    html_renderer = HTMLRenderer(settings.html_templates_path)
    vault = VaultRepository(settings.vault_path, push_after_commit=settings.vault_push_after_commit)
    idea_service = IdeaService(vault, settings.data_path)
    search_index = DocumentSearchIndex(settings.data_path, content_store, idea_service)
    extensions = ExtensionRegistry(settings.extensions_path)
    ai_configured, _ = provider_status(settings)
    agent = build_agent_executor(settings, vault, extensions) if settings.ai_enabled and ai_configured else None
    operation_registry = build_operation_registry(
        settings,
        vault,
        content_store,
        extensions,
        agent,
        idea_service,
    )
    job_runner = JobRunner(settings, job_store, content_store, vault, operation_registry)
    scheduler = Scheduler(settings, job_store, job_runner, extensions, operation_registry)
    bearer = HTTPBearer(auto_error=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        job_runner.start()
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown()
            job_runner.shutdown()

    app = FastAPI(
        title="APS Content and Automation API",
        version=__version__,
        lifespan=lifespan,
        responses=_error_responses(),
    )
    app.state.agent_executor = agent
    app.state.operation_registry = operation_registry

    def request_id(request: Request) -> str:
        return str(getattr(request.state, "request_id", "req_" + secrets.token_hex(13).upper()))

    def error_response(
        request: Request,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, object]] | None = None,
    ) -> JSONResponse:
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
            "Request does not match the API contract",
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "ROUTE_NOT_FOUND" if error.status_code == status.HTTP_404_NOT_FOUND else "HTTP_ERROR"
        message = "API route not found" if error.status_code == status.HTTP_404_NOT_FOUND else str(error.detail)
        return error_response(request, error.status_code, code, message)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An internal error occurred",
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
            raise ContentAPIError(
                status.HTTP_403_FORBIDDEN,
                "OPERATION_FORBIDDEN",
                "Content read is not allowed for this token",
            )
        return role

    app.include_router(build_content_router(content_store, html_renderer, extensions, content_reader))
    app.include_router(
        build_idea_router(
            content_store,
            html_renderer,
            idea_service,
            authenticate,
            content_reader,
        )
    )
    app.include_router(build_search_router(search_index, content_reader))
    app.include_router(build_migration_router(settings, vault, extensions, authenticate))
    app.include_router(
        build_job_router(
            settings.data_path,
            job_store,
            job_runner,
            operation_registry,
            scheduler,
            authenticate,
        )
    )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready(_: str = Depends(authenticate)) -> dict[str, object]:
        if not settings.configured:
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "DEPENDENCY_NOT_READY",
                "Core dependencies are not ready",
                [{"configured": False}],
            )
        return {"status": "ready"}

    @app.get("/v1/operations")
    def list_operations(role: str = Depends(authenticate)) -> dict[str, list[dict[str, object]]]:
        items: list[dict[str, object]] = []
        for operation in operation_registry.for_role(role):
            availability = operation_registry.availability(operation)
            item: dict[str, object] = {
                "name": operation.name.value,
                "write_mode": operation.write_mode,
                "enabled": availability.enabled,
            }
            if availability.reason is not None:
                item["disabled_reason"] = availability.reason
            items.append(item)
        return {"operations": items}

    @app.get("/v1/extensions", response_model=ExtensionListResponse)
    def list_extensions(_: str = Depends(authenticate)) -> ExtensionListResponse:
        return ExtensionListResponse(extensions=extensions.active_info())

    return app


def _error_responses() -> dict[int, dict[str, object]]:
    descriptions = {
        400: "Invalid request format",
        401: "Authentication required",
        403: "Operation forbidden",
        404: "Resource or content not found",
        409: "State or idempotency conflict",
        410: "Artifact expired",
        413: "Request content too large",
        415: "Unsupported media type",
        422: "Request validation failed",
        500: "Invalid content or internal error",
        503: "Dependency not ready",
    }
    return {
        code: {"model": ErrorResponse, "description": description}
        for code, description in descriptions.items()
    }


app = create_app()
