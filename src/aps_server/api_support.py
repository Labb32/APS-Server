"""Shared HTTP helpers used by the small route modules.

The helpers in this module deliberately know nothing about Vault paths, Git, or
providers.  Keeping that boundary narrow makes it harder for a content endpoint
to accidentally trigger generation work while serving a request.
"""

from __future__ import annotations

from typing import Callable, Literal, TypeVar

from fastapi import Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from .canonical import canonical_checksum


ContentResponse = TypeVar("ContentResponse", bound=BaseModel)


class ContentAPIError(Exception):
    """An expected API failure rendered by the application error handler."""

    def __init__(self, status_code: int, code: str, message: str, details: list[dict[str, object]] | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def content_format(format: str = Query(default="json")) -> Literal["json", "html"]:
    if format not in {"json", "html"}:
        raise ContentAPIError(status.HTTP_400_BAD_REQUEST, "INVALID_FORMAT", "format must be json or html")
    return format


def load_content(loader: Callable[[], ContentResponse]) -> ContentResponse:
    """Load one materialized result without invoking Vault or generation work."""

    try:
        return loader()
    except KeyError as error:
        raise ContentAPIError(status.HTTP_404_NOT_FOUND, "CONTENT_NOT_GENERATED", "아직 생성된 콘텐츠가 없습니다.") from error
    except (OSError, ValueError, ValidationError) as error:
        raise ContentAPIError(status.HTTP_500_INTERNAL_SERVER_ERROR, "CONTENT_INVALID", "저장된 콘텐츠가 계약을 통과하지 못했습니다.") from error


def update_data_checksum(response: ContentResponse) -> ContentResponse:
    """Recalculate the checksum after applying a response-only filter or overlay."""

    response.sha256 = canonical_checksum(getattr(response, "data"))
    return response


def html_content(document: str, checksum: str) -> HTMLResponse:
    """Return the fixed-template HTML viewer with conservative browser headers."""

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
