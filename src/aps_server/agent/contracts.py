"""Contracts shared by the Core executor, providers and official extensions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class AgentContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolAction(AgentContractModel):
    kind: Literal["tool"]
    tool: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")
    arguments: dict[str, Any] = Field(default_factory=dict)


class FinalAction(AgentContractModel):
    kind: Literal["final"]
    output: dict[str, Any]


class AgentExecutionContext(AgentContractModel):
    """Server-created execution metadata; never populated from arbitrary API fields."""

    snapshot_id: str = Field(min_length=1, max_length=128)
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTraceEntry(AgentContractModel):
    """A deliberately small trace that excludes prompts, documents and tool output."""

    step: int = Field(ge=1)
    event: Literal[
        "provider_call",
        "provider_retry",
        "tool_call",
        "tool_rejected",
        "final",
    ]
    tool: str | None = None
    code: str | None = None
    duration_ms: int = Field(default=0, ge=0)


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """One provider generation request using a JSON Schema response contract."""

    task_id: str
    instructions: str
    input: dict[str, Any]
    response_schema: dict[str, Any]
    response_schema_name: str


@dataclass(frozen=True, slots=True)
class AgentTaskSpec:
    """Server-registered task policy. Requesters cannot create or modify this object."""

    task_id: str
    mode: Literal["workflow", "tool-loop"]
    instructions: str
    output_model: type[BaseModel]
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    max_steps: int = 8
    max_input_chars: int = 200_000
    max_output_chars: int = 200_000
    max_tool_result_chars: int = 50_000
    max_calls_per_tool: int = 4
    max_side_effect_calls: int = 1
    timeout_seconds: int = 600
    validation_attempts: int = 2

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.task_id):
            raise ValueError("invalid Agent task ID")
        if self.mode not in {"workflow", "tool-loop"}:
            raise ValueError("invalid Agent task mode")
        if not self.instructions.strip():
            raise ValueError("Agent task instructions must not be blank")
        if not isinstance(self.output_model, type) or not issubclass(self.output_model, BaseModel):
            raise TypeError("Agent task output_model must be a Pydantic model")
        if self.output_model.model_config.get("extra") != "forbid":
            raise ValueError("Agent task output_model must forbid extra fields")
        if self.mode == "workflow" and self.allowed_tools:
            raise ValueError("workflow tasks cannot declare tools")
        if self.mode == "tool-loop" and not self.allowed_tools:
            raise ValueError("tool-loop tasks must declare at least one tool")
        for tool_name in self.allowed_tools:
            if not _IDENTIFIER.fullmatch(tool_name):
                raise ValueError(f"invalid Tool name in task: {tool_name}")
        if not 1 <= self.max_steps <= 8:
            raise ValueError("max_steps must be between 1 and 8")
        if not 1_000 <= self.max_input_chars <= 2_000_000:
            raise ValueError("max_input_chars must be between 1000 and 2000000")
        if not 1_000 <= self.max_output_chars <= 2_000_000:
            raise ValueError("max_output_chars must be between 1000 and 2000000")
        if not 1_000 <= self.max_tool_result_chars <= 500_000:
            raise ValueError("max_tool_result_chars must be between 1000 and 500000")
        if not 1 <= self.max_calls_per_tool <= 8:
            raise ValueError("max_calls_per_tool must be between 1 and 8")
        if not 0 <= self.max_side_effect_calls <= 1:
            raise ValueError("max_side_effect_calls must be zero or one")
        if not 10 <= self.timeout_seconds <= 7_200:
            raise ValueError("timeout_seconds must be between 10 and 7200")
        if not 1 <= self.validation_attempts <= 3:
            raise ValueError("validation_attempts must be between 1 and 3")


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    output: BaseModel
    trace: tuple[AgentTraceEntry, ...]
    steps: int
