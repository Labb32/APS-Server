"""Materialize fixed Project and Service documents without an AI runtime."""

from __future__ import annotations

import re
from pathlib import Path

from .content_models import VaultDocument, VaultDocumentsData
from .vault_files import read_vault_text


def _metadata(text: str) -> tuple[dict[str, str], str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("Vault document frontmatter is required")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Vault document frontmatter is not closed")
    fields: dict[str, str] = {}
    lines = text[4:end].splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#") or line[0].isspace():
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$", line)
        if not match:
            raise ValueError("Vault document frontmatter contains an unsupported line")
        key, value = match.groups()
        if key in fields:
            raise ValueError(f"Vault document frontmatter repeats {key}")
        value = value.split(" #", 1)[0].strip()
        if value in {"|", "|-", ">", ">-"}:
            block: list[str] = []
            while index < len(lines) and (not lines[index] or lines[index][0].isspace()):
                block.append(lines[index].strip())
                index += 1
            nonempty = [part for part in block if part]
            fields[key] = " ".join(nonempty) if value.startswith(">") else "\n".join(nonempty)
        else:
            fields[key] = value.strip("\"'")
    return fields, text[end + 5:]


def load_vault_documents(root: Path) -> dict:
    collections: dict[str, list[VaultDocument]] = {}
    for kind, directory, id_fields in (
        ("projects", "02_Projects", ("project_id", "briefing_id")),
        ("services", "03_Services", ("service_id",)),
    ):
        documents: list[VaultDocument] = []
        seen: set[str] = set()
        for path in sorted((root / directory).glob("*.md")):
            metadata, body = _metadata(read_vault_text(root, path))
            if metadata.get("type") != kind[:-1]:
                raise ValueError(f"{path.name}: type must be {kind[:-1]}")
            identifier = next((metadata[key] for key in id_fields if metadata.get(key)), "")
            if not identifier:
                raise ValueError(f"{path.name}: stable {id_fields[0]} is required")
            limit = 63 if kind == "projects" else 79
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0," + str(limit) + r"}", identifier):
                raise ValueError(f"{path.name}: Vault document ID is invalid")
            if identifier in seen:
                raise ValueError(f"{path.name}: duplicate Vault document ID {identifier}")
            seen.add(identifier)
            heading = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), path.stem)
            documents.append(VaultDocument(
                document_id=identifier,
                name=metadata.get("title") or heading,
                status=metadata.get("service_status") or metadata.get("status") or "",
                tier=metadata.get("tier") or None,
                summary=metadata.get("summary", ""),
                content=body,
                metadata={key: value for key, value in metadata.items() if key in {
                    "type", "project_id", "briefing_id", "service_id", "title", "status", "service_status",
                    "tier", "summary", "final_form", "deadline", "created", "launched_date",
                    "maintenance_cycle", "maintenance_interval_days", "last_maintenance", "maintenance_summary",
                }},
            ))
        collections[kind] = documents
    return VaultDocumentsData(**collections).model_dump(mode="json")
