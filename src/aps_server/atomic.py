"""Atomic file publication helpers for process-owned state."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def write_text(path: Path, content: str, *, newline: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline=newline)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
