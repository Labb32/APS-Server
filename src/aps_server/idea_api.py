"""Idea read, intake, curation-request, and limited update routes."""

from __future__ import annotations

import unicodedata
from typing import Callable, Literal

from fastapi import APIRouter, Depends, Header, Path as APIPath, Query, Request, status
from fastapi.responses import HTMLResponse

from .api_support import HTML_RESPONSE, ContentAPIError, content_format, html_content, load_content, update_data_checksum
from .content_models import (
    IdeaCreateRequest,
    IdeaDetailResponse,
    IdeaMergeRequest,
    IdeaMutationResponse,
    IdeaSearchRequest,
    IdeaSearchResponse,
    IdeaSetCreateRequest,
    IdeaSetDetailResponse,
    IdeaSetMutationResponse,
    IdeaSimilarResponse,
    IdeaUpdateRequest,
    IdeasResponse,
    IdeaSetsResponse,
    RecommendedIdeaSetResponse,
)
from .content_store import ContentStore
from .html_renderer import HTMLRenderer
from .idea_catalog import IdeaCatalogError
from .idea_search import search_ideas, similar_ideas
from .idea_service import IdeaService, IdeaServiceError


IdeaStatusFilter = Literal["inbox", "incubator", "organized", "proposed", "published", "archived", "all"]


def _write_error(error: Exception) -> ContentAPIError:
    code = getattr(error, "code", "IDEA_WRITE_FAILED")
    if code == "IDEA_NOT_FOUND":
        return ContentAPIError(status.HTTP_404_NOT_FOUND, code, str(error))
    if code in {"VAULT_DIRTY", "IDEA_STATUS_INVALID", "IDEA_INBOX_NOT_IGNORED", "IDEA_TRACKED_UPDATE_DISABLED", "IDEMPOTENCY_KEY_REUSED"}:
        return ContentAPIError(status.HTTP_409_CONFLICT, code, str(error))
    return ContentAPIError(status.HTTP_500_INTERNAL_SERVER_ERROR, code, str(error))


def _filter(response: IdeasResponse, idea_status: IdeaStatusFilter, idea_set_id: str | None) -> IdeasResponse:
    if idea_status != "all":
        response.data.ideas = [item for item in response.data.ideas if item.status == idea_status]
    if idea_set_id:
        response.data.idea_sets = [item for item in response.data.idea_sets if item.idea_set_id == idea_set_id]
        member_ids = {member for item in response.data.idea_sets for member in item.member_idea_ids}
        response.data.ideas = [
            item for item in response.data.ideas
            if item.idea_id in member_ids or idea_set_id in item.idea_set_ids
        ]
    return update_data_checksum(response)


def build_idea_router(
    content_store: ContentStore,
    html_renderer: HTMLRenderer,
    ideas: IdeaService,
    authenticate: Callable[..., str],
    content_reader: Callable[..., str],
) -> APIRouter:
    """Build Idea routes while retaining the app's token dependencies."""

    router = APIRouter()

    def current_content() -> IdeasResponse:
        # Inbox is intentionally overlaid at read time: intake remains cheap and
        # visible without running AI or rebuilding the committed catalog.
        response = load_content(content_store.ideas_or_empty).model_copy(deep=True)
        try:
            response.data = ideas.overlay(response.data)
        except (OSError, ValueError, KeyError, IdeaCatalogError) as error:
            raise ContentAPIError(status.HTTP_500_INTERNAL_SERVER_ERROR, "IDEA_INBOX_INVALID", str(error)) from error
        return update_data_checksum(response)

    def require_operator(role: str) -> None:
        if role != "operator":
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Idea write is not allowed for this token")

    @router.get("/v1/content/ideas", response_model=IdeasResponse, responses=HTML_RESPONSE)
    def get_ideas(
        idea_status: IdeaStatusFilter = Query(default="all", alias="status"),
        idea_set_id: str | None = Query(default=None, pattern=r"^idea_set_[A-Z0-9]+$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> IdeasResponse | HTMLResponse:
        response = _filter(current_content(), idea_status, idea_set_id)
        return html_content(html_renderer.ideas(response, idea_status), response.sha256) if format == "html" else response

    @router.get("/v1/ideas", response_model=IdeasResponse, responses=HTML_RESPONSE)
    def list_ideas(
        idea_status: IdeaStatusFilter = Query(default="all", alias="status"),
        idea_set_id: str | None = Query(default=None, pattern=r"^idea_set_[A-Z0-9]+$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> IdeasResponse | HTMLResponse:
        response = _filter(current_content(), idea_status, idea_set_id)
        return html_content(html_renderer.ideas(response, idea_status), response.sha256) if format == "html" else response

    @router.post("/v1/ideas/search", response_model=IdeaSearchResponse)
    def lexical_idea_search(request: IdeaSearchRequest, _: str = Depends(content_reader)) -> IdeaSearchResponse:
        content = current_content()
        return IdeaSearchResponse(
            query=request.query,
            vault_commit=content.vault_commit,
            results=search_ideas(content.data.ideas, request.query, request.limit),
        )

    # Register the fixed merge path before the dynamic Idea ID routes.
    @router.post("/v1/ideas/merge", response_model=IdeaMutationResponse, status_code=status.HTTP_202_ACCEPTED)
    def merge_ideas(request: IdeaMergeRequest, role: str = Depends(authenticate)) -> IdeaMutationResponse:
        require_operator(role)
        content = current_content()
        try:
            item = ideas.create_merge(request, {idea.idea_id for idea in content.data.ideas})
            return IdeaMutationResponse(idea=item, source_idea_ids=request.source_idea_ids)
        except (OSError, ValueError, IdeaServiceError) as error:
            raise _write_error(error) from error

    @router.get("/v1/ideas/{idea_id}/similar", response_model=IdeaSimilarResponse)
    def get_similar_ideas(
        idea_id: str = APIPath(pattern=r"^idea_[A-Z0-9]+$"),
        limit: int = Query(default=5, ge=1, le=50),
        _: str = Depends(content_reader),
    ) -> IdeaSimilarResponse:
        content = current_content()
        source = next((item for item in content.data.ideas if item.idea_id == idea_id), None)
        if source is None:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "IDEA_NOT_FOUND", "Idea를 찾을 수 없습니다.")
        return IdeaSimilarResponse(
            idea_id=idea_id,
            vault_commit=content.vault_commit,
            results=similar_ideas(content.data.ideas, source, limit),
        )

    @router.get("/v1/ideas/{idea_id}", response_model=IdeaDetailResponse, responses=HTML_RESPONSE)
    def get_idea(
        idea_id: str = APIPath(pattern=r"^idea_[A-Z0-9]+$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> IdeaDetailResponse | HTMLResponse:
        content = current_content()
        idea = next((item for item in content.data.ideas if item.idea_id == idea_id), None)
        if idea is None:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "IDEA_NOT_FOUND", "Idea를 찾을 수 없습니다.")
        response = IdeaDetailResponse(vault_commit=content.vault_commit, generated_at=content.generated_at, idea=idea)
        return html_content(html_renderer.idea_detail(content, idea), content.sha256) if format == "html" else response

    @router.get("/v1/idea-sets", response_model=IdeaSetsResponse, responses=HTML_RESPONSE)
    def list_idea_sets(
        status_filter: Literal["suggested", "approved", "rejected", "archived"] | None = Query(default=None, alias="status"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> IdeaSetsResponse | HTMLResponse:
        content = current_content()
        sets = [item for item in content.data.idea_sets if status_filter is None or item.status == status_filter]
        response = IdeaSetsResponse.model_validate({
            **content.model_dump(mode="json", exclude={"content_type", "data", "sha256"}),
            "data": [item.model_dump(mode="json") for item in sets], "sha256": content.sha256,
        })
        response = update_data_checksum(response)
        return html_content(html_renderer.idea_sets(response), response.sha256) if format == "html" else response

    @router.get("/v1/idea-sets/recommended", response_model=RecommendedIdeaSetResponse)
    def get_recommended_idea_set(_: str = Depends(content_reader)) -> RecommendedIdeaSetResponse:
        content = current_content()
        candidates = [item for item in content.data.idea_sets if item.status in {"suggested", "approved"}]
        if not candidates:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "IDEA_SET_NOT_FOUND", "추천할 Idea set이 없습니다.")
        candidates.sort(key=lambda item: (0 if item.status == "suggested" else 1, -len(item.member_idea_ids), item.idea_set_id))
        return RecommendedIdeaSetResponse(
            vault_commit=content.vault_commit,
            generated_at=content.generated_at,
            idea_set=candidates[0],
        )

    @router.get("/v1/idea-sets/{idea_set_id}", response_model=IdeaSetDetailResponse, responses=HTML_RESPONSE)
    def get_idea_set(
        idea_set_id: str = APIPath(pattern=r"^idea_set_[A-Z0-9]+$"),
        _: str = Depends(content_reader),
        format: Literal["json", "html"] = Depends(content_format),
    ) -> IdeaSetDetailResponse | HTMLResponse:
        content = current_content()
        item = next((item for item in content.data.idea_sets if item.idea_set_id == idea_set_id), None)
        if item is None:
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "IDEA_SET_NOT_FOUND", "Idea Set not found")
        response = IdeaSetDetailResponse(vault_commit=content.vault_commit, generated_at=content.generated_at, idea_set=item)
        return html_content(html_renderer.idea_set_detail(content, item), content.sha256) if format == "html" else response

    @router.post("/v1/ideas", response_model=IdeaMutationResponse, status_code=status.HTTP_201_CREATED)
    def create_idea(
        request: IdeaCreateRequest,
        role: str = Depends(authenticate),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", pattern=r"^[A-Za-z0-9._~-]{8,128}$"),
    ) -> IdeaMutationResponse:
        require_operator(role)
        try:
            return IdeaMutationResponse(idea=ideas.create(request, idempotency_key=idempotency_key))
        except (OSError, ValueError, IdeaServiceError) as error:
            raise _write_error(error) from error

    @router.post(
        "/v1/ideas/text",
        response_model=IdeaMutationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={413: {"description": "Text body too large"}, 415: {"description": "Unsupported media type"}},
        openapi_extra={"requestBody": {"required": True, "content": {"text/plain": {"schema": {"type": "string", "minLength": 1, "maxLength": 10000}}}}},
    )
    async def create_idea_text(
        request: Request,
        role: str = Depends(authenticate),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", pattern=r"^[A-Za-z0-9._~-]{8,128}$"),
    ) -> IdeaMutationResponse:
        require_operator(role)
        parts = [part.strip().lower() for part in request.headers.get("content-type", "").split(";")]
        if not parts or parts[0] != "text/plain" or any(part.startswith("charset=") and part != "charset=utf-8" for part in parts[1:]):
            raise ContentAPIError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_MEDIA_TYPE", "Use text/plain with UTF-8")
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 40000:
                raise ContentAPIError(status.HTTP_413_CONTENT_TOO_LARGE, "IDEA_CONTENT_TOO_LARGE", "Text exceeds 40000 bytes")
            chunks.append(chunk)
        try:
            value = b"".join(chunks).decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ContentAPIError(status.HTTP_422_UNPROCESSABLE_CONTENT, "IDEA_TEXT_INVALID", "Text must be UTF-8") from error
        value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
        if not value or len(value) > 10000 or any(unicodedata.category(char) == "Cc" and char not in "\n\t" for char in value):
            raise ContentAPIError(status.HTTP_422_UNPROCESSABLE_CONTENT, "IDEA_TEXT_INVALID", "Text must contain 1 to 10000 printable characters")
        try:
            item = ideas.create(IdeaCreateRequest(content=value), idempotency_key=idempotency_key)
            return IdeaMutationResponse(idea=item)
        except (OSError, ValueError, IdeaServiceError) as error:
            raise _write_error(error) from error

    @router.patch("/v1/ideas/{idea_id}", response_model=IdeaMutationResponse)
    def update_idea(
        request: IdeaUpdateRequest,
        idea_id: str = APIPath(pattern=r"^idea_[A-Z0-9]+$"),
        role: str = Depends(authenticate),
    ) -> IdeaMutationResponse:
        require_operator(role)
        try:
            item, commit = ideas.update(idea_id, request)
            return IdeaMutationResponse(idea=item, vault_commit=commit)
        except (OSError, ValueError, IdeaServiceError) as error:
            raise _write_error(error) from error

    @router.post("/v1/idea-sets", response_model=IdeaSetMutationResponse, status_code=status.HTTP_202_ACCEPTED)
    def create_idea_set(request: IdeaSetCreateRequest, role: str = Depends(authenticate)) -> IdeaSetMutationResponse:
        require_operator(role)
        content = current_content()
        try:
            item = ideas.create_set(request, {idea.idea_id for idea in content.data.ideas})
            return IdeaSetMutationResponse(idea_set=item)
        except (OSError, ValueError, IdeaServiceError) as error:
            raise _write_error(error) from error

    return router
