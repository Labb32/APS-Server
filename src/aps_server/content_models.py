from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Issue(ContractModel):
    code: str = Field(pattern=r"^[A-Z0-9_]+$")
    message: str = Field(max_length=1000)
    subject_id: str | None = Field(default=None, max_length=100)


class TaskItem(ContractModel):
    task_id: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    completion: str = Field(min_length=1, max_length=1000)
    status: Literal["pending", "in_progress", "blocked", "completed"]


class ServiceMaintenanceItem(ContractModel):
    service_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1, max_length=200)
    service_status: str = Field(max_length=40)
    maintenance_cycle: str | None = Field(default=None, max_length=100)
    maintenance_interval_days: int | None = Field(default=None, ge=1, le=3650)
    last_maintenance: date | None = None
    next_maintenance_due: date | None = None
    due_status: Literal["due", "overdue", "upcoming", "unknown"]
    days_overdue: int = Field(ge=0)
    maintenance_summary: str | None = Field(default=None, max_length=2000)
    issues: list[Issue] = Field(default_factory=list)


class ProjectBriefing(ContractModel):
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(max_length=40)
    tier: str | None = Field(default=None, max_length=20)
    summary: str = Field(max_length=2000)
    tasks: list[TaskItem] = Field(default_factory=list, max_length=20)
    decisions: list[str] = Field(default_factory=list, max_length=10)
    issues: list[Issue] = Field(default_factory=list, max_length=20)


class ContentEnvelope(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    content_type: str
    generated_at: datetime
    vault_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    generator_version: str = Field(min_length=1, max_length=64)
    stale: bool = False
    partial_failure: bool = False
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DailySummary(ContractModel):
    active_projects: int = Field(ge=0)
    tasks: int = Field(ge=0)
    decisions: int = Field(ge=0)
    services_due: int = Field(ge=0)


class DailyBriefingData(ContractModel):
    as_of_date: date
    summary: DailySummary
    projects: list[ProjectBriefing] = Field(default_factory=list)
    service_maintenance: list[ServiceMaintenanceItem] = Field(default_factory=list)


class DailyBriefingResponse(ContentEnvelope):
    content_type: Literal["daily_briefing"]
    data: DailyBriefingData


class ProjectCatalogItem(ContractModel):
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(max_length=40)
    tier: str | None = Field(default=None, max_length=20)
    briefing_available: bool


class ProjectCatalogData(ContractModel):
    projects: list[ProjectCatalogItem] = Field(default_factory=list)


class ProjectCatalogResponse(ContentEnvelope):
    content_type: Literal["project_catalog"]
    data: ProjectCatalogData


class ProjectBriefingData(ContractModel):
    project: ProjectBriefing


class ProjectBriefingResponse(ContentEnvelope):
    content_type: Literal["project_briefing"]
    data: ProjectBriefingData


class MaintenanceSummary(ContractModel):
    active_services: int = Field(ge=0)
    due: int = Field(ge=0)
    overdue: int = Field(ge=0)
    upcoming: int = Field(ge=0)
    unknown: int = Field(ge=0)


class ServiceMaintenanceData(ContractModel):
    as_of_date: date
    scope: Literal["due", "overdue", "upcoming", "all"]
    summary: MaintenanceSummary
    services: list[ServiceMaintenanceItem] = Field(default_factory=list)


class ServiceMaintenanceResponse(ContentEnvelope):
    content_type: Literal["service_maintenance"]
    data: ServiceMaintenanceData


class IdeaItem(ContractModel):
    idea_id: str = Field(pattern=r"^idea_[A-Z0-9]+$")
    content: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    status: Literal["received", "organized", "proposed", "published"]
    received_at: datetime
    cluster_id: str | None = Field(default=None, max_length=80)


class IdeaCluster(ContractModel):
    cluster_id: str = Field(max_length=80)
    canonical_idea: str = Field(max_length=4000)
    member_idea_ids: list[str] = Field(min_length=1)
    categories: list[str] = Field(default_factory=list)
    merge_status: Literal["suggested", "approved", "rejected"]


class IdeasData(ContractModel):
    ideas: list[IdeaItem] = Field(default_factory=list)
    clusters: list[IdeaCluster] = Field(default_factory=list)


class IdeasResponse(ContentEnvelope):
    content_type: Literal["ideas"]
    data: IdeasData


class CreateIdeaRequest(ContractModel):
    content: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class CreateIdeaResponse(ContractModel):
    idea_id: str = Field(pattern=r"^idea_[A-Z0-9]+$")
    status: Literal["received"] = "received"
    received_at: datetime


class CreateProjectRequest(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=4000)
    source_idea_ids: list[str] = Field(default_factory=list, max_length=20)
    constraints: list[str] = Field(default_factory=list, max_length=30)


class Confirmation(ContractModel):
    summary: str = Field(max_length=1000)
    planned_changes: list[str] = Field(min_length=1, max_length=20)
    expires_at: datetime


class ProjectConfirmationRequired(ContractModel):
    request_id: str = Field(pattern=r"^project_request_[A-Z0-9]+$")
    status: Literal["confirmation_required"] = "confirmation_required"
    confirmation: Confirmation


class ContentStatusItem(ContractModel):
    status: Literal["missing", "refreshing", "ready", "failed"]
    formats: list[Literal["json", "html"]] = Field(default_factory=list)
    generated_at: datetime | None = None
    stale: bool = False
    succeeded: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class ContentStatusResponse(ContractModel):
    vault_commit: str | None = None
    generated_at: datetime | None = None
    generator_version: str
    stale: bool
    content: dict[str, ContentStatusItem]
