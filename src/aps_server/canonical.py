from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json_bytes(value: BaseModel | dict[str, Any] | list[Any]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_checksum(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
