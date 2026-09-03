"""Validated dispatch for a fixed registry of Core Agent tools."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ValidationError


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
ToolHandler = Callable[[BaseModel, "ToolContext"], BaseModel | dict[str, Any]]


class ToolRegistryError(RuntimeError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Server-created state available to handlers but not serialized for the model."""

    snapshot_id: str
    services: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    capability: str
    side_effect: Literal["none", "draft"]
    handler: ToolHandler

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.name):
            raise ValueError("invalid Tool name")
        if not _IDENTIFIER.fullmatch(self.capability):
            raise ValueError("invalid Tool capability")
        if not self.description.strip():
            raise ValueError("Tool description must not be blank")
        if self.side_effect not in {"none", "draft"}:
            raise ValueError("invalid Tool side-effect policy")
        for model in (self.input_model, self.output_model):
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                raise TypeError("Tool input and output contracts must be Pydantic models")
            if model.model_config.get("extra") != "forbid":
                raise ValueError("Tool input and output contracts must forbid extra fields")


@dataclass(frozen=True, slots=True)
class ToolResult:
    output: dict[str, Any]
    side_effect: Literal["none", "draft"]


class ToolRegistry:
    """Registry populated by Core composition code before Agent work begins."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._frozen = False

    def register(self, spec: ToolSpec) -> None:
        if self._frozen:
            raise RuntimeError("Tool registry is frozen")
        if spec.name in self._tools:
            raise ValueError(f"duplicate Tool name: {spec.name}")
        self._tools[spec.name] = spec

    def freeze(self) -> None:
        self._frozen = True

    def require(self, names: frozenset[str]) -> None:
        missing = sorted(names.difference(self._tools))
        if missing:
            raise ToolRegistryError("Agent task references unavailable Tools", "TOOL_NOT_AVAILABLE")

    def descriptions(self, names: frozenset[str]) -> list[dict[str, Any]]:
        self.require(names)
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_model.model_json_schema(),
                "output_schema": spec.output_model.model_json_schema(),
                "side_effect": spec.side_effect,
            }
            for spec in sorted((self._tools[name] for name in names), key=lambda item: item.name)
        ]

    def side_effect(self, name: str) -> Literal["none", "draft"]:
        try:
            return self._tools[name].side_effect
        except KeyError as error:
            raise ToolRegistryError("requested Tool is not registered", "TOOL_NOT_AVAILABLE") from error

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        granted_capabilities: frozenset[str],
        context: ToolContext,
        max_output_chars: int,
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            raise ToolRegistryError("requested Tool is not registered", "TOOL_NOT_AVAILABLE")
        if spec.capability not in granted_capabilities:
            raise ToolRegistryError("task is not granted the Tool capability", "TOOL_CAPABILITY_DENIED")
        try:
            validated_input = spec.input_model.model_validate(arguments)
        except ValidationError as error:
            raise ToolRegistryError("Tool arguments failed schema validation", "TOOL_INPUT_INVALID") from error
        try:
            raw_output = spec.handler(validated_input, context)
            validated_output = spec.output_model.model_validate(raw_output)
        except ToolRegistryError:
            raise
        except ValidationError as error:
            raise ToolRegistryError("Tool output failed schema validation", "TOOL_OUTPUT_INVALID") from error
        except Exception as error:
            # Handler details may contain document content, paths or credentials.
            raise ToolRegistryError("Tool handler failed", "TOOL_EXECUTION_FAILED") from error
        output = validated_output.model_dump(mode="json")
        serialized = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > max_output_chars:
            raise ToolRegistryError("Tool output exceeds the task limit", "TOOL_OUTPUT_TOO_LARGE")
        return ToolResult(output=output, side_effect=spec.side_effect)
