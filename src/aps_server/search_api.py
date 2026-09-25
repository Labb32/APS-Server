"""Authenticated search route for the fixed APS document collections."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, status

from .api_support import ContentAPIError
from .content_models import DocumentSearchRequest, DocumentSearchResponse
from .document_search import DocumentSearchIndex, SearchIndexError


def build_search_router(search: DocumentSearchIndex, content_reader: Callable[..., str]) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/search", response_model=DocumentSearchResponse)
    def search_documents(
        request: DocumentSearchRequest,
        _: str = Depends(content_reader),
    ) -> DocumentSearchResponse:
        try:
            return search.search(request)
        except (OSError, ValueError, SearchIndexError) as error:
            raise ContentAPIError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "SEARCH_INDEX_INVALID",
                "검색 인덱스를 준비할 수 없습니다.",
            ) from error

    return router
