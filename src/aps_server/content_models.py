from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class VaultDocumentSummary(ContractModel):
    document_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(default="", max_length=80)
    tier: str | None = Field(default=None, max_length=20)
    summary: str = Field(default="", max_length=2000)
    metadata: dict[str, str] = Field(default_factory=dict)


class VaultDocument(VaultDocumentSummary):
    content: str = Field(max_length=50000)


class VaultDocumentsData(ContractModel):
    projects: list[VaultDocument] = Field(default_factory=list)
    services: list[VaultDocument] = Field(default_factory=list)


class VaultDocumentsResponse(ContentEnvelope):
    content_type: Literal["vault_documents"] = "vault_documents"
    data: VaultDocumentsData


class VaultDocumentListData(ContractModel):
    documents: list[VaultDocumentSummary] = Field(default_factory=list)


class VaultDocumentListResponse(ContentEnvelope):
    content_type: Literal["vault_document_list"] = "vault_document_list"
    data: VaultDocumentListData


class VaultDocumentDetailData(ContractModel):
    document: VaultDocument


class VaultDocumentDetailResponse(ContentEnvelope):
    content_type: Literal["vault_document_detail"] = "vault_document_detail"
    data: VaultDocumentDetailData


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


IdeaId = Annotated[str, Field(pattern=r"^idea_[A-Z0-9]+$")]
IdeaSetId = Annotated[str, Field(pattern=r"^idea_set_[A-Z0-9]+$")]
IdeaKeyword = Annotated[str, Field(min_length=1, max_length=80)]
SearchCollection = Literal["inbox", "idea", "idea_set", "project", "service"]


class IdeaItem(ContractModel):
    idea_id: IdeaId
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)
    status: Literal["inbox", "incubator", "organized", "proposed", "published", "archived"]
    idea_set_ids: list[IdeaSetId] = Field(default_factory=list, max_length=20)
    updated_at: datetime
    storage: Literal["vault", "inbox"] = "vault"
    commit_status: Literal["committed", "pending"] = "committed"
    content: str = Field(default="", max_length=50000)


class IdeaSet(ContractModel):
    idea_set_id: IdeaSetId
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)
    status: Literal["suggested", "approved", "rejected", "archived"]
    member_idea_ids: list[IdeaId] = Field(min_length=1, max_length=100)
    storage: Literal["vault", "inbox"] = "vault"
    commit_status: Literal["committed", "pending"] = "committed"
    content: str = Field(default="", max_length=50000)


class IdeaCreateRequest(ContractModel):
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("content", "title", "summary")
    @classmethod
    def text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
        if not value:
            raise ValueError("value must not be blank")
        if any(unicodedata.category(char) == "Cc" and char not in "\n\t" for char in value):
            raise ValueError("value contains unsupported control characters")
        return value

    @model_validator(mode="after")
    def require_content_or_canonical_fields(self) -> "IdeaCreateRequest":
        if self.content is None and (self.title is None or self.summary is None):
            raise ValueError("content or both title and summary are required")
        return self

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        value = [item.strip() for item in value]
        if any(not item or "\n" in item or "\r" in item for item in value):
            raise ValueError("keywords must be non-blank single-line strings")
        if len(set(value)) != len(value):
            raise ValueError("keywords must be unique")
        return value


class IdeaUpdateRequest(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    keywords: list[IdeaKeyword] | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, min_length=1, max_length=2000)
    status: Literal["inbox", "incubator", "organized", "proposed", "published", "archived"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "IdeaUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self

    @field_validator("title", "summary")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("keywords")
    @classmethod
    def normalize_optional_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return IdeaCreateRequest.normalize_keywords(value)


class IdeaMergeRequest(ContractModel):
    source_idea_ids: list[IdeaId] = Field(min_length=2, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)

    @field_validator("source_idea_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("source_idea_ids must be unique")
        return value

    @field_validator("title", "summary")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return str(IdeaCreateRequest.text_must_not_be_blank(value))

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        return IdeaCreateRequest.normalize_keywords(value)


class IdeaSetCreateRequest(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)
    member_idea_ids: list[IdeaId] = Field(min_length=1, max_length=100)

    @field_validator("member_idea_ids")
    @classmethod
    def unique_members(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("member_idea_ids must be unique")
        return value

    @field_validator("title", "summary")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return str(IdeaCreateRequest.text_must_not_be_blank(value))

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        return IdeaCreateRequest.normalize_keywords(value)


class NormalizedIdea(ContractModel):
    source_idea_id: IdeaId
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)

    @field_validator("title", "summary")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("curated text must not be blank")
        return value

    @field_validator("keywords")
    @classmethod
    def unique_keywords(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class IdeaMergeCandidate(ContractModel):
    source_idea_ids: list[IdeaId] = Field(min_length=2, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)

    @field_validator("title", "summary")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("merge text must not be blank")
        return value

    @field_validator("keywords")
    @classmethod
    def unique_keywords(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("source_idea_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("source_idea_ids must be unique")
        return value


class IdeaSetCandidate(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    keywords: list[IdeaKeyword] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2000)
    member_idea_ids: list[IdeaId] = Field(min_length=1, max_length=100)

    @field_validator("title", "summary")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idea Set text must not be blank")
        return value

    @field_validator("keywords")
    @classmethod
    def unique_keywords(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("member_idea_ids")
    @classmethod
    def unique_members(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("member_idea_ids must be unique")
        return value


class IdeaCurationPlan(ContractModel):
    normalized_ideas: list[NormalizedIdea] = Field(default_factory=list, max_length=100)
    merge_candidates: list[IdeaMergeCandidate] = Field(default_factory=list, max_length=20)
    set_candidates: list[IdeaSetCandidate] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class IdeaMutationResponse(ContractModel):
    idea: IdeaItem
    source_idea_ids: list[IdeaId] = Field(default_factory=list)
    vault_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,64}$")


class IdeaSetMutationResponse(ContractModel):
    idea_set: IdeaSet
    vault_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,64}$")


class IdeasData(ContractModel):
    ideas: list[IdeaItem] = Field(default_factory=list)
    idea_sets: list[IdeaSet] = Field(default_factory=list)


class IdeasResponse(ContentEnvelope):
    content_type: Literal["ideas"]
    data: IdeasData


class IdeaSearchRequest(ContractModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class IdeaSearchResult(ContractModel):
    idea_id: IdeaId
    title: str = Field(min_length=1, max_length=200)
    score: float = Field(ge=0, le=1)
    matched_by: list[Literal["title", "keyword", "summary"]] = Field(default_factory=list)


class IdeaSearchResponse(ContractModel):
    query: str
    search_mode: Literal["lexical"] = "lexical"
    index_provider: Literal["aps-server"] = "aps-server"
    vault_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    results: list[IdeaSearchResult] = Field(default_factory=list)


class IdeaSimilarResponse(ContractModel):
    idea_id: IdeaId
    search_mode: Literal["lexical"] = "lexical"
    index_provider: Literal["aps-server"] = "aps-server"
    vault_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    results: list[IdeaSearchResult] = Field(default_factory=list)


class DocumentSearchRequest(ContractModel):
    query: str = Field(min_length=1, max_length=200)
    collections: list[SearchCollection] = Field(default_factory=list, max_length=5)
    statuses: list[str] = Field(default_factory=list, max_length=20)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def normalized_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

    @field_validator("collections", "statuses")
    @classmethod
    def unique_filters(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 80 for value in normalized):
            raise ValueError("filters must be non-blank and at most 80 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("filters must be unique")
        return normalized


class DocumentSearchResult(ContractModel):
    collection: SearchCollection
    document_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    status: str = Field(default="", max_length=80)
    summary: str = Field(default="", max_length=500)
    score: float = Field(ge=0, le=1)
    matched_by: list[Literal["title", "keyword", "summary", "embedding"]] = Field(default_factory=list)


class DocumentSearchResponse(ContractModel):
    query: str
    search_mode: Literal["hybrid", "lexical_fallback"]
    index_provider: Literal["aps-server"] = "aps-server"
    embedding_model: str | None = Field(default=None, max_length=100)
    index_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    indexed_at: datetime
    stale: bool = False
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    next_offset: int | None = Field(default=None, ge=0)
    results: list[DocumentSearchResult] = Field(default_factory=list)


class IdeaDetailResponse(ContractModel):
    vault_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    generated_at: datetime
    idea: IdeaItem


class RecommendedIdeaSetResponse(ContractModel):
    vault_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    generated_at: datetime
    idea_set: IdeaSet


class IdeaSetDetailResponse(ContractModel):
    vault_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    generated_at: datetime
    idea_set: IdeaSet


class IdeaSetsResponse(ContentEnvelope):
    content_type: Literal["idea_sets"] = "idea_sets"
    data: list[IdeaSet] = Field(default_factory=list)


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
