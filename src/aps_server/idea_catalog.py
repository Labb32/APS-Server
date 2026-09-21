from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .vault_files import read_vault_text


class IdeaCatalogError(RuntimeError):
    pass


IDEA_INBOX_DIRECTORY = "00_Inbox"
IDEA_DIRECTORY = "01_Ideas"
IDEA_SET_DIRECTORY = "01_Idea_Sets"


_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):(?:\s*(.*))?$")


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _frontmatter(path: Path, vault_root: Path) -> dict[str, Any]:
    text = read_vault_text(vault_root, path).replace("\r\n", "\n")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise IdeaCatalogError(f"{path.name}: frontmatter is required")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        raise IdeaCatalogError(f"{path.name}: frontmatter is not closed") from error

    metadata: dict[str, Any] = {}
    index = 1
    while index < end:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = _KEY.fullmatch(line)
        if not match:
            raise IdeaCatalogError(f"{path.name}: unsupported frontmatter line {index + 1}")
        key, raw_value = match.groups()
        if key in metadata:
            raise IdeaCatalogError(f"{path.name}: duplicate {key}")
        raw_value = (raw_value or "").strip()
        index += 1

        if raw_value in {">", ">-", "|", "|-"}:
            block: list[str] = []
            while index < end and (not lines[index] or lines[index][0].isspace()):
                block.append(lines[index].strip())
                index += 1
            metadata[key] = " ".join(part for part in block if part) if raw_value.startswith(">") else "\n".join(block).strip()
            continue

        if not raw_value:
            values: list[str] = []
            while index < end and re.match(r"^\s+-\s*", lines[index]):
                values.append(_scalar(re.sub(r"^\s+-\s*", "", lines[index])))
                index += 1
            metadata[key] = values if values else None
            continue

        if raw_value == "[]":
            metadata[key] = []
        else:
            metadata[key] = _scalar(raw_value)

    return metadata


def _markdown_body(path: Path, vault_root: Path) -> str:
    text = read_vault_text(vault_root, path).replace("\r\n", "\n")
    lines = text.splitlines(keepends=True)
    closing = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if closing is None:
        raise IdeaCatalogError(f"{path.name}: frontmatter is not closed")
    body = "".join(lines[closing + 1:]).lstrip("\n")
    if len(body) > 50000:
        raise IdeaCatalogError(f"{path.name}: Markdown body exceeds 50000 characters")
    return body


def _required_string(metadata: dict[str, Any], key: str, path: Path) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IdeaCatalogError(f"{path.name}: {key} is required")
    return value.strip()


def _string_list(metadata: dict[str, Any], key: str, path: Path) -> list[str]:
    value = metadata.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise IdeaCatalogError(f"{path.name}: {key} must be a string list")
    return list(dict.fromkeys(item.strip() for item in value))


def _timestamp(value: str, path: Path) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise IdeaCatalogError(f"{path.name}: updated_at must be ISO 8601") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def load_idea_catalog(vault_root: Path) -> dict[str, list[dict[str, Any]]]:
    idea_directory = vault_root / IDEA_DIRECTORY
    if not idea_directory.is_dir():
        raise IdeaCatalogError("Vault 01_Ideas directory is missing")

    ideas: list[dict[str, Any]] = []
    seen_idea_ids: set[str] = set()
    for path in sorted(idea_directory.glob("*.md"), key=lambda item: item.name.casefold()):
        metadata = _frontmatter(path, vault_root)
        if metadata.get("type") != "idea":
            raise IdeaCatalogError(f"{path.name}: type must be idea")
        idea_id = _required_string(metadata, "idea_id", path)
        if idea_id in seen_idea_ids:
            raise IdeaCatalogError(f"{path.name}: duplicate idea_id {idea_id}")
        seen_idea_ids.add(idea_id)
        ideas.append(
            {
                "idea_id": idea_id,
                "title": _required_string(metadata, "title", path),
                "keywords": _string_list(metadata, "keywords", path),
                "summary": _required_string(metadata, "summary", path),
                "status": _required_string(metadata, "status", path),
                "idea_set_ids": _string_list(metadata, "idea_set_ids", path),
                "updated_at": _timestamp(_required_string(metadata, "updated_at", path), path),
                "content": _markdown_body(path, vault_root),
            }
        )

    idea_sets: list[dict[str, Any]] = []
    seen_set_ids: set[str] = set()
    set_directory = vault_root / IDEA_SET_DIRECTORY
    if set_directory.is_dir():
        for path in sorted(set_directory.glob("*.md"), key=lambda item: item.name.casefold()):
            metadata = _frontmatter(path, vault_root)
            if metadata.get("type") != "idea_set":
                raise IdeaCatalogError(f"{path.name}: type must be idea_set")
            idea_set_id = _required_string(metadata, "idea_set_id", path)
            if idea_set_id in seen_set_ids:
                raise IdeaCatalogError(f"{path.name}: duplicate idea_set_id {idea_set_id}")
            seen_set_ids.add(idea_set_id)
            members = _string_list(metadata, "member_idea_ids", path)
            if not members:
                raise IdeaCatalogError(f"{path.name}: member_idea_ids must not be empty")
            unknown = sorted(set(members) - seen_idea_ids)
            if unknown:
                raise IdeaCatalogError(f"{path.name}: unknown member Idea IDs: {', '.join(unknown)}")
            idea_sets.append(
                {
                    "idea_set_id": idea_set_id,
                    "title": _required_string(metadata, "title", path),
                    "keywords": _string_list(metadata, "keywords", path),
                    "summary": _required_string(metadata, "summary", path),
                    "status": _required_string(metadata, "status", path),
                    "member_idea_ids": members,
                    "content": _markdown_body(path, vault_root),
                }
            )

    missing_sets = sorted(
        {idea_set_id for idea in ideas for idea_set_id in idea["idea_set_ids"]} - seen_set_ids
    )
    if missing_sets:
        raise IdeaCatalogError(f"Ideas reference missing Idea sets: {', '.join(missing_sets)}")

    return {"ideas": ideas, "idea_sets": idea_sets}
