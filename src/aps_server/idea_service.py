"""Constrained Idea writes for the ignored Inbox and curated Idea folders.

This is intentionally not a generic Vault editor. Pending intake is confined
to ``00_Inbox``; only validated curation reaches a tracked path and Git commit.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .content_models import (
    IdeaCreateRequest,
    IdeaCurationPlan,
    IdeaItem,
    IdeaMergeRequest,
    IdeaSet,
    IdeaSetCreateRequest,
    IdeaUpdateRequest,
    IdeasData,
)
from .canonical import canonical_checksum
from .idea_catalog import (
    IDEA_DIRECTORY,
    IDEA_INBOX_DIRECTORY,
    IDEA_SET_DIRECTORY,
    IdeaCatalogError,
    _frontmatter,
    _markdown_body,
    load_idea_catalog,
)
from .vault import VaultPushError, VaultRepository
from .vault_files import read_vault_bytes, read_vault_text


class IdeaServiceError(RuntimeError):
    def __init__(self, message: str, code: str = "IDEA_WRITE_FAILED") -> None:
        super().__init__(message)
        self.code = code


def _id(prefix: str) -> str:
    return prefix + secrets.token_hex(10).upper()


def _list_block(name: str, values: list[str]) -> list[str]:
    if not values:
        return [f"{name}: []"]
    return [f"{name}:", *(f"  - {value}" for value in values)]


def _block(name: str, value: str) -> list[str]:
    parts = [part.strip() for part in value.replace("\r\n", "\n").splitlines() if part.strip()]
    return [f"{name}: >-", *(f"  {part}" for part in parts)]


def _body(vault_root: Path, path: Path) -> str | None:
    if not path.is_file():
        return None
    text = read_vault_text(vault_root, path).replace("\r\n", "\n")
    parts = text.split("---", 2)
    return parts[2].lstrip("\n") if len(parts) == 3 else None


def _render_idea(
    item: IdeaItem,
    created_at: str,
    body: str | None = None,
    merge_sources: list[str] | None = None,
    intake_key_hash: str | None = None,
    intake_request_hash: str | None = None,
) -> str:
    lines = ["---", "type: idea", f"idea_id: {item.idea_id}", *_block("title", item.title)]
    lines.extend(_list_block("keywords", item.keywords))
    lines.extend(_block("summary", item.summary))
    lines.extend(["idea_type: general", f"status: {item.status}"])
    lines.extend(_list_block("idea_set_ids", item.idea_set_ids))
    if merge_sources:
        lines.extend(_list_block("merge_source_idea_ids", merge_sources))
    if intake_key_hash:
        lines.extend([f"intake_key_hash: {intake_key_hash}", f"intake_request_hash: {intake_request_hash}"])
    lines.extend([f"created_at: {created_at}", f"updated_at: {item.updated_at.isoformat()}", "---", ""])
    return "\n".join(lines) + (body if body is not None else f"# {item.title}\n\n{item.summary}\n")


def _render_set(item: IdeaSet, created_at: str) -> str:
    lines = ["---", "type: idea_set", f"idea_set_id: {item.idea_set_id}", *_block("title", item.title)]
    lines.extend(_list_block("keywords", item.keywords))
    lines.extend(_block("summary", item.summary))
    lines.append(f"status: {item.status}")
    lines.extend(_list_block("member_idea_ids", item.member_idea_ids))
    lines.extend([f"created_at: {created_at}", f"updated_at: {datetime.now(UTC).isoformat()}", "---", ""])
    return "\n".join(lines) + f"# {item.title}\n\n{item.summary}\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class IdeaService:
    def __init__(self, vault: VaultRepository) -> None:
        self.vault = vault
        self.inbox = vault.root / IDEA_INBOX_DIRECTORY
        self._lock = threading.RLock()

    def _require_ignored(self, path: Path) -> None:
        if not self.vault.is_ignored(path):
            raise IdeaServiceError("Vault 00_Inbox must be Git-ignored before Idea intake", "IDEA_INBOX_NOT_IGNORED")

    @staticmethod
    def _idea_from_metadata(metadata: dict[str, Any], storage: str) -> IdeaItem:
        return IdeaItem.model_validate(
            {
                "idea_id": metadata["idea_id"],
                "title": metadata["title"],
                "keywords": metadata.get("keywords") or [],
                "summary": metadata["summary"],
                "status": metadata["status"],
                "idea_set_ids": metadata.get("idea_set_ids") or [],
                "updated_at": metadata["updated_at"],
                "storage": storage,
                "commit_status": "pending" if storage == "inbox" else "committed",
            }
        )

    def pending(self) -> IdeasData:
        ideas: list[IdeaItem] = []
        idea_sets: list[IdeaSet] = []
        if not self.inbox.is_dir():
            return IdeasData()
        for path in sorted(self.inbox.glob("idea_*.md")):
            metadata = _frontmatter(path, self.vault.root)
            if metadata.get("type") == "idea":
                ideas.append(self._idea_from_metadata(metadata, "inbox").model_copy(update={"content": _markdown_body(path, self.vault.root)}))
            elif metadata.get("type") == "idea_set":
                idea_sets.append(
                    IdeaSet.model_validate(
                        {
                            "idea_set_id": metadata["idea_set_id"],
                            "title": metadata["title"],
                            "keywords": metadata.get("keywords") or [],
                            "summary": metadata["summary"],
                            "status": metadata["status"],
                            "member_idea_ids": metadata.get("member_idea_ids") or [],
                            "storage": "inbox",
                            "commit_status": "pending",
                            "content": _markdown_body(path, self.vault.root),
                        }
                    )
                )
        return IdeasData(ideas=ideas, idea_sets=idea_sets)

    def overlay(self, committed: IdeasData) -> IdeasData:
        # API reads include uncurated local intake without putting Inbox files
        # into Git or pretending they are committed records.
        pending = self.pending()
        ideas = {item.idea_id: item for item in committed.ideas}
        ideas.update({item.idea_id: item for item in pending.ideas})
        sets = {item.idea_set_id: item for item in committed.idea_sets}
        sets.update({item.idea_set_id: item for item in pending.idea_sets})
        return IdeasData(ideas=list(ideas.values()), idea_sets=list(sets.values()))

    def create(
        self,
        request: IdeaCreateRequest,
        merge_sources: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> IdeaItem:
        now = datetime.now(UTC)
        content = request.content or request.summary or ""
        first_line = next((line.strip() for line in content.splitlines() if line.strip()), "Untitled Idea")
        title = request.title or first_line[:200]
        summary = request.summary or content[:2000]
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
        request_hash = canonical_checksum(request)
        with self._lock, self.vault.locked():
            if key_hash:
                for directory, storage in ((self.inbox, "inbox"), (self.vault.root / IDEA_DIRECTORY, "vault")):
                    if not directory.is_dir():
                        continue
                    for path in directory.glob("*.md"):
                        metadata = _frontmatter(path, self.vault.root)
                        if metadata.get("intake_key_hash") != key_hash:
                            continue
                        if metadata.get("intake_request_hash") != request_hash:
                            raise IdeaServiceError("Idempotency-Key belongs to a different Idea request", "IDEMPOTENCY_KEY_REUSED")
                        return self._idea_from_metadata(metadata, storage).model_copy(update={"content": _markdown_body(path, self.vault.root)})
            item = IdeaItem(
                idea_id=_id("idea_"), title=title, keywords=request.keywords,
                summary=summary, status="inbox", idea_set_ids=[], updated_at=now,
                storage="inbox", commit_status="pending",
            )
            self._require_ignored(self.inbox / f"{item.idea_id}.md")
            body = f"# {item.title}\n\n{content}\n"
            item = item.model_copy(update={"content": body})
            _atomic_write(
                self.inbox / f"{item.idea_id}.md",
                _render_idea(item, now.date().isoformat(), body=body, merge_sources=merge_sources,
                             intake_key_hash=key_hash, intake_request_hash=request_hash),
            )
        return item

    def create_merge(self, request: IdeaMergeRequest, available_ids: set[str]) -> IdeaItem:
        missing = sorted(set(request.source_idea_ids) - available_ids)
        if missing:
            raise IdeaServiceError(f"unknown source Idea IDs: {', '.join(missing)}", "IDEA_NOT_FOUND")
        return self.create(
            IdeaCreateRequest(title=request.title, keywords=request.keywords, summary=request.summary),
            merge_sources=request.source_idea_ids,
        )

    def create_set(self, request: IdeaSetCreateRequest, available_ids: set[str]) -> IdeaSet:
        missing = sorted(set(request.member_idea_ids) - available_ids)
        if missing:
            raise IdeaServiceError(f"unknown member Idea IDs: {', '.join(missing)}", "IDEA_NOT_FOUND")
        now = datetime.now(UTC)
        item = IdeaSet(
            idea_set_id=_id("idea_set_"), title=request.title.strip(), keywords=list(dict.fromkeys(request.keywords)),
            summary=request.summary.strip(), status="suggested", member_idea_ids=request.member_idea_ids,
            storage="inbox", commit_status="pending",
            content=f"# {request.title.strip()}\n\n{request.summary.strip()}\n",
        )
        with self._lock, self.vault.locked():
            self._require_ignored(self.inbox / f"{item.idea_set_id}.md")
            _atomic_write(self.inbox / f"{item.idea_set_id}.md", _render_set(item, now.date().isoformat()))
        return item

    def _find_committed(self, idea_id: str) -> Path | None:
        directory = self.vault.root / IDEA_DIRECTORY
        for path in directory.glob("*.md"):
            if _frontmatter(path, self.vault.root).get("idea_id") == idea_id:
                return path
        return None

    def update(self, idea_id: str, request: IdeaUpdateRequest) -> tuple[IdeaItem, str | None]:
        with self._lock, self.vault.locked():
            pending_path = self.inbox / f"{idea_id}.md"
            if not pending_path.is_file():
                if self._find_committed(idea_id):
                    raise IdeaServiceError("Tracked Idea updates require a proposal and approval flow", "IDEA_TRACKED_UPDATE_DISABLED")
                raise IdeaServiceError("Idea not found", "IDEA_NOT_FOUND")
            path = pending_path
            metadata = _frontmatter(path, self.vault.root)
            current = self._idea_from_metadata(metadata, "inbox")
            changes = request.model_dump(exclude_unset=True)
            updated = current.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
            created_at = str(metadata.get("created_at") or updated.updated_at.date().isoformat())
            merge_sources = metadata.get("merge_source_idea_ids") or []
            if updated.status != "inbox":
                raise IdeaServiceError("pending Idea status must remain inbox", "IDEA_STATUS_INVALID")
            self._require_ignored(path)
            body = _body(self.vault.root, path)
            _atomic_write(path, _render_idea(
                updated, created_at, body, merge_sources,
                metadata.get("intake_key_hash"), metadata.get("intake_request_hash"),
            ))
            return updated.model_copy(update={"content": body or ""}), None

    def curate(self, plan: IdeaCurationPlan | None = None) -> dict[str, list[dict[str, Any]]]:
        with self._lock, self.vault.locked():
            self.vault.require_clean()
            pending = self.pending()
            if not pending.ideas and not pending.idea_sets:
                return load_idea_catalog(self.vault.root)
            committed_catalog = IdeasData.model_validate(load_idea_catalog(self.vault.root))
            pending_ids = {item.idea_id for item in pending.ideas}
            available_ids = pending_ids | {item.idea_id for item in committed_catalog.ideas}
            normalizations = {item.source_idea_id: item for item in (plan.normalized_ideas if plan else [])}
            if len(normalizations) != len(plan.normalized_ideas if plan else []):
                raise IdeaServiceError("curation plan contains duplicate normalized Idea IDs", "IDEA_CURATION_INVALID")
            unknown_normalizations = sorted(set(normalizations) - pending_ids)
            if unknown_normalizations:
                raise IdeaServiceError("curation plan normalizes unknown or committed Ideas", "IDEA_CURATION_INVALID")
            merge_groups: set[frozenset[str]] = set()
            for candidate in plan.merge_candidates if plan else []:
                if not set(candidate.source_idea_ids).issubset(available_ids) or not pending_ids.intersection(candidate.source_idea_ids):
                    raise IdeaServiceError("merge candidate contains invalid source Ideas", "IDEA_CURATION_INVALID")
                group = frozenset(candidate.source_idea_ids)
                if group in merge_groups:
                    raise IdeaServiceError("curation plan contains duplicate merge candidates", "IDEA_CURATION_INVALID")
                merge_groups.add(group)
            set_groups: set[frozenset[str]] = set()
            for candidate in plan.set_candidates if plan else []:
                if not set(candidate.member_idea_ids).issubset(available_ids) or not pending_ids.intersection(candidate.member_idea_ids):
                    raise IdeaServiceError("Idea Set candidate contains invalid member Ideas", "IDEA_CURATION_INVALID")
                group = frozenset(candidate.member_idea_ids)
                if group in set_groups:
                    raise IdeaServiceError("curation plan contains duplicate Idea Set candidates", "IDEA_CURATION_INVALID")
                set_groups.add(group)
            destinations: list[Path] = []
            originals: dict[Path, bytes | None] = {}
            source_paths: list[Path] = []
            try:
                # Build every destination first, validate the complete catalog,
                # then create one commit.  The rollback below preserves the
                # previous worktree if any document fails validation.
                for item in pending.ideas:
                    source = self.inbox / f"{item.idea_id}.md"
                    metadata = _frontmatter(source, self.vault.root)
                    destination = self.vault.root / IDEA_DIRECTORY / f"{item.idea_id}.md"
                    if self._find_committed(item.idea_id):
                        source_paths.append(source)
                        continue
                    originals[destination] = read_vault_bytes(self.vault.root, destination) if destination.exists() else None
                    normalized = normalizations.get(item.idea_id)
                    changes = (
                        {
                            "title": normalized.title,
                            "keywords": normalized.keywords,
                            "summary": normalized.summary,
                        }
                        if normalized is not None
                        else {}
                    )
                    committed = item.model_copy(
                        update={
                            **changes,
                            "status": "incubator",
                            "storage": "vault",
                            "commit_status": "committed",
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    _atomic_write(
                        destination,
                        _render_idea(
                            committed,
                            str(metadata.get("created_at") or committed.updated_at.date()),
                            _body(self.vault.root, source),
                            metadata.get("merge_source_idea_ids") or [],
                            metadata.get("intake_key_hash"),
                            metadata.get("intake_request_hash"),
                        ),
                    )
                    destinations.append(destination)
                    source_paths.append(source)
                for candidate in plan.merge_candidates if plan else []:
                    now = datetime.now(UTC)
                    merged = IdeaItem(
                        idea_id=_id("idea_"),
                        title=candidate.title,
                        keywords=candidate.keywords,
                        summary=candidate.summary,
                        status="incubator",
                        idea_set_ids=[],
                        updated_at=now,
                        storage="vault",
                        commit_status="committed",
                    )
                    destination = self.vault.root / IDEA_DIRECTORY / f"{merged.idea_id}.md"
                    originals[destination] = None
                    _atomic_write(
                        destination,
                        _render_idea(
                            merged,
                            now.date().isoformat(),
                            merge_sources=candidate.source_idea_ids,
                        ),
                    )
                    destinations.append(destination)
                    available_ids.add(merged.idea_id)
                for item in pending.idea_sets:
                    source = self.inbox / f"{item.idea_set_id}.md"
                    metadata = _frontmatter(source, self.vault.root)
                    destination = self.vault.root / IDEA_SET_DIRECTORY / f"{item.idea_set_id}.md"
                    originals[destination] = read_vault_bytes(self.vault.root, destination) if destination.exists() else None
                    committed = item.model_copy(update={"storage": "vault", "commit_status": "committed"})
                    _atomic_write(
                        destination,
                        _render_set(committed, str(metadata.get("created_at") or datetime.now(UTC).date().isoformat())),
                    )
                    destinations.append(destination)
                    source_paths.append(source)
                for candidate in plan.set_candidates if plan else []:
                    now = datetime.now(UTC)
                    suggested = IdeaSet(
                        idea_set_id=_id("idea_set_"),
                        title=candidate.title,
                        keywords=candidate.keywords,
                        summary=candidate.summary,
                        status="suggested",
                        member_idea_ids=candidate.member_idea_ids,
                        storage="vault",
                        commit_status="committed",
                    )
                    destination = self.vault.root / IDEA_SET_DIRECTORY / f"{suggested.idea_set_id}.md"
                    originals[destination] = None
                    _atomic_write(destination, _render_set(suggested, now.date().isoformat()))
                    destinations.append(destination)
                catalog = load_idea_catalog(self.vault.root)
                if destinations:
                    self.vault.commit_paths(
                        destinations,
                        f"ideas: curate {len(source_paths)} inbox item(s), {len(destinations)} document(s)",
                    )
            except VaultPushError:
                raise
            except Exception:
                for path, content in originals.items():
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(content)
                raise
            for path in source_paths:
                path.unlink(missing_ok=True)
            return catalog
