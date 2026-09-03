"""Bounded workflow and JSON-action execution for Core-registered Agent tasks."""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .contracts import (
    AgentExecutionContext,
    AgentExecutionResult,
    AgentTaskSpec,
    AgentTraceEntry,
    FinalAction,
    ModelRequest,
    ToolAction,
)
from .providers import ModelProvider, ModelProviderError
from .tools import ToolContext, ToolRegistry, ToolRegistryError


class _ActionEnvelope(BaseModel):
    """Single-root wire schema normalized into ToolAction or FinalAction."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "final"]
    tool: str | None
    arguments: dict[str, Any] | None
    output: dict[str, Any] | None

    @model_validator(mode="after")
    def require_action_fields(self) -> "_ActionEnvelope":
        if self.kind == "tool":
            if self.tool is None or self.arguments is None or self.output is not None:
                raise ValueError("tool action fields are inconsistent")
        elif self.tool is not None or self.arguments is not None or self.output is None:
            raise ValueError("final action fields are inconsistent")
        return self

    def action(self) -> ToolAction | FinalAction:
        if self.kind == "tool":
            return ToolAction(kind="tool", tool=self.tool or "", arguments=self.arguments or {})
        return FinalAction(kind="final", output=self.output or {})


class AgentExecutionError(RuntimeError):
    def __init__(self, message: str, code: str = "AGENT_EXECUTION_FAILED") -> None:
        super().__init__(message)
        self.code = code


class AgentTaskRegistry:
    """A startup-only registry preventing request-created Agent policies."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTaskSpec] = {}
        self._frozen = False

    def register(self, spec: AgentTaskSpec) -> None:
        if self._frozen:
            raise RuntimeError("Agent task registry is frozen")
        if spec.task_id in self._tasks:
            raise ValueError(f"duplicate Agent task ID: {spec.task_id}")
        self._tasks[spec.task_id] = spec

    def freeze(self) -> None:
        self._frozen = True

    def get(self, task_id: str) -> AgentTaskSpec:
        try:
            return self._tasks[task_id]
        except KeyError as error:
            raise AgentExecutionError("Agent task is not registered", "AGENT_TASK_NOT_AVAILABLE") from error

    def task_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._tasks))

    def specs(self) -> tuple[AgentTaskSpec, ...]:
        return tuple(self._tasks[task_id] for task_id in sorted(self._tasks))


class AgentExecutor:
    """Run fixed Agent tasks without owning Jobs, Vault commits or publications."""

    def __init__(self, provider: ModelProvider, tasks: AgentTaskRegistry, tools: ToolRegistry | None = None) -> None:
        self.provider = provider
        self.tasks = tasks
        self.tools = tools or ToolRegistry()
        for task in self.tasks.specs():
            self.tools.require(task.allowed_tools)
        # Registration is a composition-time concern. Once an Executor exists,
        # no runtime request or extension process can mutate its policy surface.
        self.tasks.freeze()
        self.tools.freeze()

    def execute(
        self,
        task_id: str,
        task_input: dict[str, Any],
        context: AgentExecutionContext,
        tool_context: ToolContext | None = None,
    ) -> AgentExecutionResult:
        spec = self.tasks.get(task_id)
        self._require_json_size(task_input, spec.max_input_chars, "AGENT_INPUT_TOO_LARGE")
        if spec.mode == "workflow":
            return self._workflow(spec, task_input, context)
        if tool_context is None:
            tool_context = ToolContext(snapshot_id=context.snapshot_id)
        if tool_context.snapshot_id != context.snapshot_id:
            raise AgentExecutionError("Tool context does not match the Agent snapshot", "AGENT_SNAPSHOT_MISMATCH")
        self.tools.require(spec.allowed_tools)
        return self._tool_loop(spec, task_input, context, tool_context)

    def _workflow(
        self,
        spec: AgentTaskSpec,
        task_input: dict[str, Any],
        context: AgentExecutionContext,
    ) -> AgentExecutionResult:
        deadline = time.monotonic() + spec.timeout_seconds
        trace: list[AgentTraceEntry] = []
        provider_input = self._base_input(task_input, context)
        for attempt in range(1, spec.validation_attempts + 1):
            if attempt > 1:
                provider_input["validation_feedback"] = {
                    "code": "OUTPUT_SCHEMA_INVALID",
                    "instruction": "Return a new complete result matching the response schema.",
                }
                trace.append(AgentTraceEntry(step=attempt, event="provider_retry", code="OUTPUT_SCHEMA_INVALID"))
            started = time.monotonic()
            raw = self._generate(
                spec,
                provider_input,
                spec.output_model.model_json_schema(),
                deadline,
            )
            trace.append(
                AgentTraceEntry(
                    step=attempt,
                    event="provider_call",
                    duration_ms=self._duration_ms(started),
                )
            )
            try:
                output = spec.output_model.model_validate(raw)
            except ValidationError as error:
                if attempt == spec.validation_attempts:
                    raise AgentExecutionError(
                        "Agent output failed schema validation",
                        "AGENT_OUTPUT_INVALID",
                    ) from error
                continue
            trace.append(AgentTraceEntry(step=attempt, event="final"))
            return AgentExecutionResult(output=output, trace=tuple(trace), steps=attempt)
        raise AgentExecutionError("Agent workflow did not produce a result", "AGENT_OUTPUT_INVALID")

    def _tool_loop(
        self,
        spec: AgentTaskSpec,
        task_input: dict[str, Any],
        context: AgentExecutionContext,
        tool_context: ToolContext,
    ) -> AgentExecutionResult:
        deadline = time.monotonic() + spec.timeout_seconds
        trace: list[AgentTraceEntry] = []
        history: list[dict[str, Any]] = []
        call_counts = {name: 0 for name in spec.allowed_tools}
        side_effect_calls = 0
        accumulated_tool_chars = 0
        tool_descriptions = self.tools.descriptions(spec.allowed_tools)
        action_schema = self._action_schema(spec, tool_descriptions)
        instructions = (
            spec.instructions.rstrip()
            + "\nChoose exactly one action per response. Use kind='tool' to call an allowed Tool "
            "or kind='final' to return the complete task output. For a tool action set output=null; "
            "for a final action set tool=null and arguments=null. Never invent Tool names or filesystem paths."
        )

        for step in range(1, spec.max_steps + 1):
            model_input = self._base_input(task_input, context)
            model_input["tools"] = tool_descriptions
            model_input["history"] = history
            self._require_json_size(model_input, spec.max_input_chars, "AGENT_CONTEXT_TOO_LARGE")
            started = time.monotonic()
            raw = self._generate(spec, model_input, action_schema, deadline, instructions=instructions)
            trace.append(
                AgentTraceEntry(
                    step=step,
                    event="provider_call",
                    duration_ms=self._duration_ms(started),
                )
            )
            try:
                action = _ActionEnvelope.model_validate(raw).action()
            except ValidationError as error:
                history.append({"type": "error", "code": "ACTION_SCHEMA_INVALID"})
                trace.append(AgentTraceEntry(step=step, event="provider_retry", code="ACTION_SCHEMA_INVALID"))
                if step == spec.max_steps:
                    raise AgentExecutionError("Agent action failed schema validation", "AGENT_ACTION_INVALID") from error
                continue

            if isinstance(action, FinalAction):
                try:
                    output = spec.output_model.model_validate(action.output)
                except ValidationError as error:
                    history.append({"type": "error", "code": "FINAL_OUTPUT_INVALID"})
                    trace.append(AgentTraceEntry(step=step, event="provider_retry", code="FINAL_OUTPUT_INVALID"))
                    if step == spec.max_steps:
                        raise AgentExecutionError("Agent final output failed schema validation", "AGENT_OUTPUT_INVALID") from error
                    continue
                trace.append(AgentTraceEntry(step=step, event="final"))
                return AgentExecutionResult(output=output, trace=tuple(trace), steps=step)

            if action.tool not in spec.allowed_tools:
                raise AgentExecutionError("Agent requested a Tool outside its task policy", "AGENT_TOOL_FORBIDDEN")
            self._require_deadline(deadline)
            call_counts[action.tool] += 1
            if call_counts[action.tool] > spec.max_calls_per_tool:
                raise AgentExecutionError("Agent exceeded the per-Tool call limit", "AGENT_TOOL_LIMIT")
            side_effect = self.tools.side_effect(action.tool)
            if side_effect != "none":
                if side_effect_calls >= spec.max_side_effect_calls:
                    raise AgentExecutionError("Agent exceeded the side-effect Tool limit", "AGENT_SIDE_EFFECT_LIMIT")
                # Reserve the allowance before dispatch. A failed handler may
                # still have produced an external draft and must not be retried.
                side_effect_calls += 1
            try:
                result = self.tools.execute(
                    action.tool,
                    action.arguments,
                    context.capabilities,
                    tool_context,
                    spec.max_tool_result_chars,
                )
            except ToolRegistryError as error:
                history.append({"type": "tool_error", "tool": action.tool, "code": error.code})
                trace.append(AgentTraceEntry(step=step, event="tool_rejected", tool=action.tool, code=error.code))
                if step == spec.max_steps:
                    raise AgentExecutionError("Agent Tool call failed", error.code) from error
                continue
            self._require_deadline(deadline)
            if result.side_effect != side_effect:
                raise AgentExecutionError("Tool side-effect policy changed during execution", "AGENT_TOOL_POLICY_INVALID")
            serialized = json.dumps(result.output, ensure_ascii=False, separators=(",", ":"))
            accumulated_tool_chars += len(serialized)
            if accumulated_tool_chars > spec.max_tool_result_chars:
                raise AgentExecutionError("Agent Tool results exceed the task limit", "AGENT_CONTEXT_TOO_LARGE")
            history.append({"type": "tool_result", "tool": action.tool, "output": result.output})
            trace.append(AgentTraceEntry(step=step, event="tool_call", tool=action.tool))

        raise AgentExecutionError("Agent reached the maximum number of steps", "AGENT_STEP_LIMIT")

    def _generate(
        self,
        spec: AgentTaskSpec,
        provider_input: dict[str, Any],
        response_schema: dict[str, Any],
        deadline: float,
        instructions: str | None = None,
    ) -> dict[str, Any]:
        self._require_json_size(provider_input, spec.max_input_chars, "AGENT_CONTEXT_TOO_LARGE")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentExecutionError("Agent task timed out", "AGENT_TIMEOUT")
        request = ModelRequest(
            task_id=spec.task_id,
            instructions=instructions or spec.instructions,
            input=provider_input,
            response_schema=response_schema,
            response_schema_name=self._schema_name(spec.task_id),
        )
        try:
            output = self.provider.generate(request, max(1, math.ceil(remaining)))
        except ModelProviderError as error:
            raise AgentExecutionError("Agent model provider failed", error.code) from error
        self._require_json_size(
            output,
            spec.max_output_chars,
            "AGENT_OUTPUT_TOO_LARGE",
            subject="Agent output",
        )
        return output

    @staticmethod
    def _base_input(task_input: dict[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {
            "task_input": task_input,
            "execution": {
                "snapshot_id": context.snapshot_id,
                "metadata": context.metadata,
            },
        }

    @staticmethod
    def _action_schema(spec: AgentTaskSpec, tool_descriptions: list[dict[str, Any]]) -> dict[str, Any]:
        argument_schemas = [item["input_schema"] for item in tool_descriptions]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "tool", "arguments", "output"],
            "properties": {
                "kind": {"type": "string", "enum": ["tool", "final"]},
                "tool": {
                    "anyOf": [
                        {"type": "string", "enum": sorted(spec.allowed_tools)},
                        {"type": "null"},
                    ]
                },
                "arguments": {"anyOf": [*argument_schemas, {"type": "null"}]},
                "output": {
                    "anyOf": [
                        spec.output_model.model_json_schema(),
                        {"type": "null"},
                    ]
                },
            },
        }

    @staticmethod
    def _require_json_size(value: Any, limit: int, code: str, subject: str = "Agent input") -> None:
        try:
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise AgentExecutionError(f"{subject} must be JSON serializable", "AGENT_INPUT_INVALID") from error
        if len(serialized) > limit:
            raise AgentExecutionError(f"{subject} exceeds the task limit", code)

    @staticmethod
    def _require_deadline(deadline: float) -> None:
        if time.monotonic() >= deadline:
            raise AgentExecutionError("Agent task timed out", "AGENT_TIMEOUT")

    @staticmethod
    def _schema_name(task_id: str) -> str:
        return ("aps_" + re.sub(r"[^a-zA-Z0-9_-]", "_", task_id))[:64]

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, round((time.monotonic() - started) * 1000))
