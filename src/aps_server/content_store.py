"""Validated canonical-JSON storage for materialized API content."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .canonical import canonical_checksum, canonical_json_bytes
from .content_models import (
    ContentStatusItem,
    ContentStatusResponse,
    DailyBriefingData,
    DailyBriefingResponse,
    IdeasResponse,
    IdeasData,
    MaintenanceSummary,
    ProjectBriefingData,
    ProjectBriefingResponse,
    ProjectCatalogData,
    ProjectCatalogItem,
    ProjectCatalogResponse,
    ServiceMaintenanceData,
    ServiceMaintenanceResponse,
    VaultDocumentsData,
    VaultDocumentsResponse,
)


ContentModel = TypeVar("ContentModel", bound=BaseModel)
DataModel = TypeVar("DataModel", bound=BaseModel)


class ContentValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContentPublication:
    response: BaseModel
    path: Path
    content_url: str

    @property
    def content_type(self) -> str:
        return str(getattr(self.response, "content_type"))

    @property
    def sha256(self) -> str:
        return str(getattr(self.response, "sha256"))

    @property
    def generated_at(self) -> datetime:
        return getattr(self.response, "generated_at")


class ContentStore:
    def __init__(self, data_path: Path, generator_version: str = "0.1.0") -> None:
        self.root = data_path / "content"
        self.projects_path = self.root / "projects"
        for path in (self.root, self.projects_path):
            path.mkdir(parents=True, exist_ok=True)
        self.generator_version = generator_version
        self._lock = threading.RLock()

    @classmethod
    def _read(cls, path: Path, model: type[ContentModel]) -> ContentModel:
        if not path.is_file():
            raise KeyError(path.name)
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Verify the serialized payload before Pydantic normalization can alter
        # defaults or representation and hide on-disk corruption.
        if not isinstance(raw, dict) or raw.get("sha256") != canonical_checksum(raw.get("data")):
            raise ValueError("stored content checksum does not match canonical data")
        value = model.model_validate(raw)
        return value

    @staticmethod
    def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    def _build(
        self,
        response_model: type[ContentModel],
        data_model: type[DataModel],
        content_type: str,
        raw_data: dict[str, Any],
        vault_commit: str,
        generated_at: datetime,
        partial_failure: bool = False,
    ) -> ContentModel:
        try:
            data = data_model.model_validate(raw_data)
            return response_model.model_validate(
                {
                    "schema_version": "1.0",
                    "content_type": content_type,
                    "generated_at": generated_at,
                    "vault_commit": vault_commit,
                    "generator_version": self.generator_version,
                    "stale": False,
                    "partial_failure": partial_failure,
                    "sha256": canonical_checksum(data),
                    "data": data.model_dump(mode="json"),
                }
            )
        except ValidationError as error:
            raise ContentValidationError(str(error)) from error

    @staticmethod
    def _maintenance_data(as_of_date: Any, services: list[Any]) -> dict[str, Any]:
        statuses = [item.get("due_status") for item in services if isinstance(item, dict)]
        return {
            "as_of_date": as_of_date,
            "scope": "all",
            "summary": {
                "active_services": len(services),
                "due": statuses.count("due"),
                "overdue": statuses.count("overdue"),
                "upcoming": statuses.count("upcoming"),
                "unknown": statuses.count("unknown"),
            },
            "services": services,
        }

    def _daily_publications(
        self,
        payload: dict[str, Any],
        vault_commit: str,
        generated_at: datetime,
    ) -> list[ContentPublication]:
        raw_data = self._payload_data(payload)
        partial_failure = bool(payload.get("partial_failure", False))
        daily = self._build(
            DailyBriefingResponse,
            DailyBriefingData,
            "daily_briefing",
            raw_data,
            vault_commit,
            generated_at,
            partial_failure,
        )

        catalog_data = ProjectCatalogData(
            projects=[
                ProjectCatalogItem(
                    project_id=project.project_id,
                    name=project.name,
                    status=project.status,
                    tier=project.tier,
                    briefing_available=True,
                )
                for project in daily.data.projects
            ]
        )
        catalog = self._build(
            ProjectCatalogResponse,
            ProjectCatalogData,
            "project_catalog",
            catalog_data.model_dump(mode="json"),
            vault_commit,
            generated_at,
            partial_failure,
        )

        service_data = self._maintenance_data(
            daily.data.as_of_date,
            [item.model_dump(mode="json") for item in daily.data.service_maintenance],
        )
        maintenance = self._build(
            ServiceMaintenanceResponse,
            ServiceMaintenanceData,
            "service_maintenance",
            service_data,
            vault_commit,
            generated_at,
            partial_failure,
        )

        publications = [
            ContentPublication(daily, self.root / "daily_briefing.json", "/v1/content/briefing/daily"),
            ContentPublication(catalog, self.root / "project_catalog.json", "/v1/content/projects"),
            ContentPublication(maintenance, self.root / "service_maintenance.json", "/v1/content/services/maintenance"),
        ]
        for project in daily.data.projects:
            project_response = self._build(
                ProjectBriefingResponse,
                ProjectBriefingData,
                "project_briefing",
                {"project": project.model_dump(mode="json")},
                vault_commit,
                generated_at,
                partial_failure,
            )
            publications.append(
                ContentPublication(
                    project_response,
                    self.projects_path / f"{project.project_id}.json",
                    f"/v1/content/projects/{project.project_id}/briefing",
                )
            )
        return publications

    def _project_publication(
        self,
        payload: dict[str, Any],
        vault_commit: str,
        generated_at: datetime,
    ) -> ContentPublication:
        raw_data = self._payload_data(payload)
        partial_failure = bool(payload.get("partial_failure", False))
        if "project" not in raw_data:
            projects = raw_data.get("projects")
            if isinstance(projects, list) and len(projects) == 1:
                raw_data = {"project": projects[0]}
            elif "project_id" in raw_data:
                raw_data = {"project": raw_data}
        project = self._build(
            ProjectBriefingResponse,
            ProjectBriefingData,
            "project_briefing",
            raw_data,
            vault_commit,
            generated_at,
            partial_failure,
        )
        project_id = project.data.project.project_id
        return ContentPublication(
            project,
            self.projects_path / f"{project_id}.json",
            f"/v1/content/projects/{project_id}/briefing",
        )

    def _service_publication(
        self,
        payload: dict[str, Any],
        vault_commit: str,
        generated_at: datetime,
    ) -> ContentPublication:
        raw_data = self._payload_data(payload)
        partial_failure = bool(payload.get("partial_failure", False))
        if "scope" not in raw_data or "summary" not in raw_data or "services" not in raw_data:
            services = raw_data.get("services", raw_data.get("service_maintenance", raw_data.get("maintenance", [])))
            if not isinstance(services, list):
                services = []
            raw_data = self._maintenance_data(
                raw_data.get("as_of_date", raw_data.get("date")),
                services,
            )
        maintenance = self._build(
            ServiceMaintenanceResponse,
            ServiceMaintenanceData,
            "service_maintenance",
            raw_data,
            vault_commit,
            generated_at,
            partial_failure,
        )
        return ContentPublication(
            maintenance,
            self.root / "service_maintenance.json",
            "/v1/content/services/maintenance",
        )

    def _ideas_publication(
        self,
        payload: dict[str, Any],
        vault_commit: str,
        generated_at: datetime,
    ) -> ContentPublication:
        ideas = self._build(
            IdeasResponse,
            IdeasData,
            "ideas",
            self._payload_data(payload),
            vault_commit,
            generated_at,
        )
        return ContentPublication(ideas, self.root / "ideas.json", "/v1/content/ideas")

    def prepare_daily(self, payload: dict[str, Any], vault_commit: str) -> list[ContentPublication]:
        return self._daily_publications(payload, vault_commit, datetime.now(UTC))

    def prepare_project(self, payload: dict[str, Any], vault_commit: str) -> list[ContentPublication]:
        return [self._project_publication(payload, vault_commit, datetime.now(UTC))]

    def prepare_service(self, payload: dict[str, Any], vault_commit: str) -> list[ContentPublication]:
        return [self._service_publication(payload, vault_commit, datetime.now(UTC))]

    def prepare_ideas(self, payload: dict[str, Any], vault_commit: str) -> list[ContentPublication]:
        return [self._ideas_publication(payload, vault_commit, datetime.now(UTC))]

    def prepare_vault_content(self, payload: dict[str, Any], vault_commit: str) -> list[ContentPublication]:
        now = datetime.now(UTC)
        documents = self._build(VaultDocumentsResponse, VaultDocumentsData, "vault_documents", payload["documents"], vault_commit, now)
        return [
            ContentPublication(documents, self.root / "vault_documents.json", "/v1/content/vault"),
            self._ideas_publication(payload["ideas"], vault_commit, now),
        ]

    def vault_documents(self) -> VaultDocumentsResponse:
        return self._read(self.root / "vault_documents.json", VaultDocumentsResponse)

    def publish(self, publications: list[ContentPublication]) -> None:
        temporary_paths: list[tuple[Path, Path]] = []
        with self._lock:
            try:
                for publication in publications:
                    publication.path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = publication.path.with_suffix(publication.path.suffix + ".tmp")
                    temporary.write_bytes(canonical_json_bytes(publication.response))
                    temporary_paths.append((temporary, publication.path))
                for temporary, destination in temporary_paths:
                    temporary.replace(destination)
            finally:
                for temporary, _ in temporary_paths:
                    temporary.unlink(missing_ok=True)

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
                content[name] = ContentStatusItem(status="failed", failed=1)
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
