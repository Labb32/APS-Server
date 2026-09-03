"""Read-only, ID-based Vault tools registered by APS Core."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...content_models import IdeaItem, IdeaSearchResult, IdeasData
from ...idea_catalog import load_idea_catalog
from ...idea_search import search_ideas
from ...vault import VaultRepository
from .registry import ToolContext, ToolRegistry, ToolRegistryError, ToolSpec


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchInput(ToolModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=20)


class IdeaIdInput(ToolModel):
    idea_id: str = Field(pattern=r"^idea_[A-Z0-9]+$")


class ProjectIdInput(ToolModel):
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class ServiceIdInput(ToolModel):
    service_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")


class IdeaSearchOutput(ToolModel):
    results: list[IdeaSearchResult] = Field(default_factory=list, max_length=20)


class IdeaReadOutput(ToolModel):
    idea: IdeaItem


class DocumentSummary(ToolModel):
    document_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    status: str = Field(default="", max_length=80)


class DocumentSearchOutput(ToolModel):
    results: list[DocumentSummary] = Field(default_factory=list, max_length=20)


class DocumentReadOutput(DocumentSummary):
    content: str = Field(max_length=50_000)


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if not text.startswith("---"):
        return text[:50_000]
    parts = text.split("---", 2)
    return (parts[2].lstrip("\n") if len(parts) == 3 else text)[:50_000]


def _document_metadata(path: Path) -> dict[str, str]:
    """Extract only supported top-level text fields from general Vault YAML.

    Project and Service documents may contain richer YAML than Idea files.
    Read tools deliberately ignore that structure instead of treating it as a
    writable or general-purpose configuration format.
    """

    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---", 2)
    if len(parts) != 3:
        return {}
    lines = parts[1].splitlines()
    wanted = {"title", "summary", "status", "service_status", "project_id", "briefing_id", "service_id"}
    metadata: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):(?:\s*(.*))?$", lines[index])
        index += 1
        if match is None or match.group(1) not in wanted:
            continue
        key, raw = match.group(1), (match.group(2) or "").strip()
        if raw in {">", ">-", "|", "|-"}:
            block: list[str] = []
            while index < len(lines) and (not lines[index] or lines[index][0].isspace()):
                block.append(lines[index].strip())
                index += 1
            raw = " ".join(item for item in block if item)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            raw = raw[1:-1]
        metadata[key] = raw
    return metadata


def _title(path: Path, metadata: dict[str, Any], body: str) -> str:
    value = metadata.get("title")
    if isinstance(value, str) and value.strip():
        return value.strip()[:200]
    for line in body.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()[:200]
    return path.stem[:200]


def _document(path: Path, id_fields: tuple[str, ...], fallback_id: str) -> DocumentReadOutput:
    metadata = _document_metadata(path)
    body = _body(path)
    document_id = next(
        (
            str(metadata[field]).strip()
            for field in id_fields
            if isinstance(metadata.get(field), str) and str(metadata[field]).strip()
        ),
        fallback_id,
    )
    raw_summary = metadata.get("summary")
    summary = str(raw_summary).strip() if isinstance(raw_summary, str) else ""
    return DocumentReadOutput(
        document_id=document_id,
        title=_title(path, metadata, body),
        summary=summary[:2000],
        status=str(metadata.get("status") or metadata.get("service_status") or "")[:80],
        content=body,
    )


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return (slug or "service")[:72].rstrip("-")


def _project_documents(root: Path) -> list[DocumentReadOutput]:
    directory = root / "02_Projects"
    return [
        _document(path, ("project_id", "briefing_id"), _slug(path.stem))
        for path in sorted(directory.glob("*.md"), key=lambda item: item.name.casefold())
    ] if directory.is_dir() else []


def _service_documents(root: Path) -> list[DocumentReadOutput]:
    directory = root / "03_Services"
    return [
        _document(path, ("service_id",), _slug(path.stem))
        for path in sorted(directory.glob("*.md"), key=lambda item: item.name.casefold())
    ] if directory.is_dir() else []


def _search_documents(documents: list[DocumentReadOutput], request: SearchInput) -> DocumentSearchOutput:
    query = unicodedata.normalize("NFKC", request.query).casefold().strip()
    ranked: list[tuple[float, DocumentSummary]] = []
    for document in documents:
        title = unicodedata.normalize("NFKC", document.title).casefold()
        summary = unicodedata.normalize("NFKC", document.summary).casefold()
        score = SequenceMatcher(None, query, title).ratio() * 0.6
        if query in title:
            score += 0.3
        elif query in summary:
            score += 0.15
        if score < 0.1:
            continue
        ranked.append(
            (
                score,
                DocumentSummary(
                    document_id=document.document_id,
                    title=document.title,
                    summary=document.summary,
                    status=document.status,
                ),
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1].title.casefold(), item[1].document_id))
    return DocumentSearchOutput(results=[item[1] for item in ranked[: request.limit]])


def build_core_tool_registry(vault: VaultRepository, fixed_snapshot_id: str | None = None) -> ToolRegistry:
    registry = ToolRegistry()

    def require_snapshot(context: ToolContext) -> None:
        current_snapshot = fixed_snapshot_id or vault.commit()
        if current_snapshot != context.snapshot_id:
            raise ToolRegistryError("Vault changed after the Agent snapshot was fixed", "TOOL_SNAPSHOT_CHANGED")

    def idea_data(context: ToolContext) -> IdeasData:
        require_snapshot(context)
        return IdeasData.model_validate(load_idea_catalog(vault.root))

    def search_idea(request: BaseModel, context: ToolContext) -> IdeaSearchOutput:
        validated = SearchInput.model_validate(request)
        return IdeaSearchOutput(results=search_ideas(idea_data(context).ideas, validated.query, validated.limit))

    def read_idea(request: BaseModel, context: ToolContext) -> IdeaReadOutput:
        validated = IdeaIdInput.model_validate(request)
        item = next((idea for idea in idea_data(context).ideas if idea.idea_id == validated.idea_id), None)
        if item is None:
            raise KeyError(validated.idea_id)
        return IdeaReadOutput(idea=item)

    def search_project(request: BaseModel, context: ToolContext) -> DocumentSearchOutput:
        require_snapshot(context)
        return _search_documents(_project_documents(vault.root), SearchInput.model_validate(request))

    def read_project(request: BaseModel, context: ToolContext) -> DocumentReadOutput:
        require_snapshot(context)
        validated = ProjectIdInput.model_validate(request)
        item = next((doc for doc in _project_documents(vault.root) if doc.document_id == validated.project_id), None)
        if item is None:
            raise KeyError(validated.project_id)
        return item

    def read_service(request: BaseModel, context: ToolContext) -> DocumentReadOutput:
        require_snapshot(context)
        validated = ServiceIdInput.model_validate(request)
        item = next((doc for doc in _service_documents(vault.root) if doc.document_id == validated.service_id), None)
        if item is None:
            raise KeyError(validated.service_id)
        return item

    registry.register(
        ToolSpec(
            name="vault.search_ideas",
            description="Search Idea titles, keywords and summaries in the fixed APS Idea catalog.",
            input_model=SearchInput,
            output_model=IdeaSearchOutput,
            capability="vault.idea.read",
            side_effect="none",
            handler=search_idea,
        )
    )
    registry.register(
        ToolSpec(
            name="vault.read_idea",
            description="Read one Idea by its APS Idea ID.",
            input_model=IdeaIdInput,
            output_model=IdeaReadOutput,
            capability="vault.idea.read",
            side_effect="none",
            handler=read_idea,
        )
    )
    registry.register(
        ToolSpec(
            name="vault.search_projects",
            description="Search fixed APS Project documents and return metadata summaries.",
            input_model=SearchInput,
            output_model=DocumentSearchOutput,
            capability="vault.project.read",
            side_effect="none",
            handler=search_project,
        )
    )
    registry.register(
        ToolSpec(
            name="vault.read_project",
            description="Read one APS Project document by project ID.",
            input_model=ProjectIdInput,
            output_model=DocumentReadOutput,
            capability="vault.project.read",
            side_effect="none",
            handler=read_project,
        )
    )
    registry.register(
        ToolSpec(
            name="vault.read_service",
            description="Read one APS Service document by service ID.",
            input_model=ServiceIdInput,
            output_model=DocumentReadOutput,
            capability="vault.service.read",
            side_effect="none",
            handler=read_service,
        )
    )
    return registry
