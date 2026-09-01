"""Read-only routes for pre-generated canonical content."""

from __future__ import annotations

from typing import Callable, Literal

from fastapi import APIRouter, Depends, Path as APIPath
from fastapi.responses import HTMLResponse

from .api_support import content_format, html_content, load_content, update_data_checksum
from .content_models import (
    ContentStatusResponse,
    DailyBriefingResponse,
    ProjectBriefingResponse,
    ProjectCatalogResponse,
    ServiceMaintenanceResponse,
)
from .content_store import ContentStore
from .html_renderer import HTMLRenderer


def build_content_router(
    content_store: ContentStore,
    html_renderer: HTMLRenderer,
    content_reader: Callable[..., str],
) -> APIRouter:
    """Build content routes with application-owned authentication dependencies."""

    router = APIRouter()

    @router.get("/v1/content/briefing/daily", response_model=DailyBriefingResponse)
    def get_daily_briefing(
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> DailyBriefingResponse | HTMLResponse:
        response = load_content(content_store.daily_briefing)
        return html_content(html_renderer.daily_briefing(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/projects", response_model=ProjectCatalogResponse)
    def get_project_catalog(
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ProjectCatalogResponse | HTMLResponse:
        response = load_content(content_store.project_catalog)
        return html_content(html_renderer.project_catalog(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/projects/{project_id}/briefing", response_model=ProjectBriefingResponse)
    def get_project_briefing(
        project_id: str = APIPath(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ProjectBriefingResponse | HTMLResponse:
        response = load_content(lambda: content_store.project_briefing(project_id))
        return html_content(html_renderer.project_briefing(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/services/maintenance", response_model=ServiceMaintenanceResponse)
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
        return html_content(html_renderer.service_maintenance(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/status", response_model=ContentStatusResponse)
    def get_content_status(_: str = Depends(content_reader)) -> ContentStatusResponse:
        return content_store.status()

    return router
