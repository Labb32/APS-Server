"""Read-only routes for pre-generated canonical content."""

from __future__ import annotations

from typing import Callable, Literal

from fastapi import APIRouter, Depends, Path as APIPath, Query, status
from fastapi.responses import HTMLResponse

from .api_support import HTML_RESPONSE, ContentAPIError, content_format, html_content, load_content, update_data_checksum
from .content_models import (
    ContentStatusResponse,
    DailyBriefingResponse,
    ProjectBriefingResponse,
    ProjectCatalogResponse,
    ServiceMaintenanceResponse,
    VaultDocumentDetailResponse,
    VaultDocumentListResponse,
    VaultDocumentsResponse,
)
from .content_store import ContentStore
from .extensions import ExtensionRegistry
from .html_renderer import HTMLRenderer


def build_content_router(
    content_store: ContentStore,
    html_renderer: HTMLRenderer,
    extensions: ExtensionRegistry,
    content_reader: Callable[..., str],
) -> APIRouter:
    """Build content routes with application-owned authentication dependencies."""

    router = APIRouter()

    def briefing_reader(role: str = Depends(content_reader)) -> str:
        if not extensions.is_installed("briefing"):
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "EXTENSION_NOT_READY",
                "Briefing extension is not installed",
            )
        return role

    @router.get("/v1/content/vault", response_model=VaultDocumentsResponse, responses=HTML_RESPONSE)
    def get_vault_documents(
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> VaultDocumentsResponse | HTMLResponse:
        response = load_content(content_store.vault_documents)
        return html_content(html_renderer.vault_documents(response), response.sha256) if format == "html" else response

    def document_response(collection: Literal["projects", "services"], identifier: str | None = None, status_filter: str | None = None):
        source: VaultDocumentsResponse = load_content(content_store.vault_documents)
        documents = getattr(source.data, collection)
        if identifier is not None:
            document = next((item for item in documents if item.document_id == identifier), None)
            if document is None:
                code = "PROJECT_NOT_FOUND" if collection == "projects" else "SERVICE_NOT_FOUND"
                raise ContentAPIError(status.HTTP_404_NOT_FOUND, code, f"{collection[:-1].title()} not found")
            data = {"document": document.model_dump(mode="json")}
            response = VaultDocumentDetailResponse.model_validate({
                **source.model_dump(mode="json", exclude={"data", "content_type", "sha256"}),
                "data": data, "sha256": source.sha256,
            })
        else:
            if status_filter is not None:
                documents = [item for item in documents if item.status == status_filter]
            data = {"documents": [item.model_dump(mode="json", exclude={"content"}) for item in documents]}
            response = VaultDocumentListResponse.model_validate({
                **source.model_dump(mode="json", exclude={"data", "content_type", "sha256"}),
                "data": data, "sha256": source.sha256,
            })
        return update_data_checksum(response)

    @router.get("/v1/projects", response_model=VaultDocumentListResponse, responses=HTML_RESPONSE)
    def list_projects(
        status_filter: str | None = Query(default=None, alias="status", max_length=80),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> VaultDocumentListResponse | HTMLResponse:
        response = document_response("projects", status_filter=status_filter)
        return html_content(html_renderer.vault_document_list(response, "projects"), response.sha256) if format == "html" else response

    @router.get("/v1/projects/{project_id}", response_model=VaultDocumentDetailResponse, responses=HTML_RESPONSE)
    def get_project(
        project_id: str = APIPath(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> VaultDocumentDetailResponse | HTMLResponse:
        response = document_response("projects", identifier=project_id)
        return html_content(html_renderer.vault_document_detail(response, "projects"), response.sha256) if format == "html" else response

    @router.get("/v1/services", response_model=VaultDocumentListResponse, responses=HTML_RESPONSE)
    def list_services(
        status_filter: str | None = Query(default=None, alias="status", max_length=80),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> VaultDocumentListResponse | HTMLResponse:
        response = document_response("services", status_filter=status_filter)
        return html_content(html_renderer.vault_document_list(response, "services"), response.sha256) if format == "html" else response

    @router.get("/v1/services/{service_id}", response_model=VaultDocumentDetailResponse, responses=HTML_RESPONSE)
    def get_service(
        service_id: str = APIPath(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> VaultDocumentDetailResponse | HTMLResponse:
        response = document_response("services", identifier=service_id)
        return html_content(html_renderer.vault_document_detail(response, "services"), response.sha256) if format == "html" else response

    @router.get("/v1/content/briefing/daily", response_model=DailyBriefingResponse, responses=HTML_RESPONSE)
    def get_daily_briefing(
        _: str = Depends(briefing_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> DailyBriefingResponse | HTMLResponse:
        response = load_content(content_store.daily_briefing)
        return html_content(html_renderer.daily_briefing(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/projects", response_model=ProjectCatalogResponse, responses=HTML_RESPONSE)
    def get_project_catalog(
        _: str = Depends(briefing_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ProjectCatalogResponse | HTMLResponse:
        response = load_content(content_store.project_catalog)
        return html_content(html_renderer.project_catalog(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/projects/{project_id}/briefing", response_model=ProjectBriefingResponse, responses=HTML_RESPONSE)
    def get_project_briefing(
        project_id: str = APIPath(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"),
        _: str = Depends(briefing_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> ProjectBriefingResponse | HTMLResponse:
        response = load_content(lambda: content_store.project_briefing(project_id))
        return html_content(html_renderer.project_briefing(response), response.sha256) if format == "html" else response

    @router.get("/v1/content/services/maintenance", response_model=ServiceMaintenanceResponse, responses=HTML_RESPONSE)
    def get_service_maintenance(
        scope: Literal["due", "overdue", "upcoming", "all"] = "due",
        _: str = Depends(briefing_reader),
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
        response = content_store.status()
        if not extensions.is_installed("briefing"):
            briefing_types = {
                "daily_briefing",
                "project_catalog",
                "project_briefing",
                "service_maintenance",
            }
            response.content = {
                content_type: item
                for content_type, item in response.content.items()
                if content_type not in briefing_types
            }
        return response

    return router
