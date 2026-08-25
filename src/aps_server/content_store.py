from __future__ import annotations

import json
import secrets
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .content_models import (
    ContentStatusItem,
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


ContentModel = TypeVar("ContentModel", bound=BaseModel)


class ContentStore:
    def __init__(self, data_path: Path, generator_version: str = "0.1.0") -> None:
        self.root = data_path / "content"
        self.projects_path = self.root / "projects"
        self.ideas_path = data_path / "staging" / "ideas"
        self.project_requests_path = data_path / "staging" / "project-requests"
        for path in (self.root, self.projects_path, self.ideas_path, self.project_requests_path):
            path.mkdir(parents=True, exist_ok=True)
        self.generator_version = generator_version
        self._lock = threading.RLock()

    @staticmethod
    def _read(path: Path, model: type[ContentModel]) -> ContentModel:
        if not path.is_file():
            raise KeyError(path.name)
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, model: BaseModel) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def daily_briefing(self) -> DailyBriefingResponse:
        return self._read(self.root / "daily_briefing.json", DailyBriefingResponse)

    def project_catalog(self) -> ProjectCatalogResponse:
        return self._read(self.root / "project_catalog.json", ProjectCatalogResponse)

    def project_briefing(self, project_id: str) -> ProjectBriefingResponse:
        return self._read(self.projects_path / f"{project_id}.json", ProjectBriefingResponse)

    def service_maintenance(self) -> ServiceMaintenanceResponse:
        return self._read(self.root / "service_maintenance.json", ServiceMaintenanceResponse)

    def ideas(self) -> IdeasResponse:
        return self._read(self.root / "ideas.json", IdeasResponse)

    def create_idea(self, request: CreateIdeaRequest) -> CreateIdeaResponse:
        response = CreateIdeaResponse(
            idea_id="idea_" + secrets.token_hex(13).upper(),
            received_at=datetime.now(UTC),
        )
        stored = {
            **response.model_dump(mode="json"),
            "content": request.content,
            "tags": list(dict.fromkeys(request.tags)),
        }
        path = self.ideas_path / f"{response.idea_id}.json"
        temporary = path.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        return response

    def create_project_request(self, request: CreateProjectRequest) -> ProjectConfirmationRequired:
        request_id = "project_request_" + secrets.token_hex(13).upper()
        response = ProjectConfirmationRequired(
            request_id=request_id,
            confirmation={
                "summary": f"'{request.title}' 프로젝트 문서와 ProjectContext 초안을 생성합니다.",
                "planned_changes": [
                    "프로젝트 문서 초안 생성",
                    "ProjectContext brief와 초기 Task 생성",
                    "간단한 마일스톤과 일정 제안",
                ],
                "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            },
        )
        stored = {
            "request": request.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
            "status": response.status,
        }
        path = self.project_requests_path / f"{request_id}.json"
        temporary = path.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        return response

    def status(self) -> ContentStatusResponse:
        sources: dict[str, tuple[Path, type[BaseModel]]] = {
            "daily_briefing": (self.root / "daily_briefing.json", DailyBriefingResponse),
            "project_catalog": (self.root / "project_catalog.json", ProjectCatalogResponse),
            "service_maintenance": (self.root / "service_maintenance.json", ServiceMaintenanceResponse),
            "ideas": (self.root / "ideas.json", IdeasResponse),
        }
        content: dict[str, ContentStatusItem] = {}
        commits: list[str] = []
        generated: list[datetime] = []
        stale = False
        for name, (path, model) in sources.items():
            if not path.is_file():
                content[name] = ContentStatusItem(status="missing")
                continue
            try:
                value = self._read(path, model)
            except (OSError, ValueError):
                content[name] = ContentStatusItem(status="failed")
                continue
            item_stale = bool(getattr(value, "stale", False))
            content[name] = ContentStatusItem(
                status="ready",
                formats=["json", "html"],
                generated_at=getattr(value, "generated_at"),
                stale=item_stale,
                succeeded=1,
            )
            commits.append(getattr(value, "vault_commit"))
            generated.append(getattr(value, "generated_at"))
            stale = stale or item_stale
        return ContentStatusResponse(
            vault_commit=commits[0] if commits and len(set(commits)) == 1 else None,
            generated_at=max(generated) if generated else None,
            generator_version=self.generator_version,
            stale=stale,
            content=content,
        )
