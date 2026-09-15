"""Materialize fixed Project and Service documents without an AI runtime."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .content_models import VaultDocument, VaultDocumentsData
from .vault_files import read_vault_text


def _metadata(text: str) -> tuple[dict[str, str], str]:
    text = text.replace("\r\n", "\n")
    parts = text.split("---", 2) if text.startswith("---\n") else []
    if len(parts) != 3:
        return {}, text
    fields: dict[str, str] = {}
    lines = iter(parts[1].splitlines())
    # Supported metadata consists of top-level scalars. Ignore richer YAML;
    # preserve the body for clients instead of guessing its meaning.
    for line in lines:
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            value = match[2].split(" #", 1)[0].strip()
            if value not in {"|", "|-", ">", ">-"}:
                fields[match[1]] = value.strip("\"'")
    return fields, parts[2].lstrip("\n")


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
            identifier = next((metadata[key] for key in id_fields if metadata.get(key)), "")
            if not identifier:
                prefix = "project" if kind == "projects" else "service"
                identifier = prefix + "-" + hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]
            limit = 63 if kind == "projects" else 79
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0," + str(limit) + r"}", identifier):
                raise ValueError("Vault document ID is invalid")
            if identifier in seen:
                raise ValueError("Vault document IDs must be unique within a catalog")
            seen.add(identifier)
            heading = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), path.stem)
            documents.append(VaultDocument(
                document_id=identifier,
                name=(metadata.get("title") or heading)[:200],
                status=(metadata.get("service_status") or metadata.get("status") or "")[:80],
                tier=(metadata.get("tier") or "")[:20] or None,
                summary=metadata.get("summary", "")[:2000],
                content=body[:50000],
            ))
        collections[kind] = documents
    return VaultDocumentsData(**collections).model_dump(mode="json")
