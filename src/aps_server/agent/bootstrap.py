"""Composition helpers for the Core-owned Agent runtime."""

from __future__ import annotations

from ..config import Settings
from ..extensions import ExtensionRegistry
from ..vault import VaultRepository
from .executor import AgentExecutor, AgentTaskRegistry
from .providers import create_model_provider
from .tasks import idea_curation_task
from .tools import build_core_tool_registry


def build_agent_executor(
    settings: Settings,
    vault: VaultRepository,
    extensions: ExtensionRegistry,
    fixed_snapshot_id: str | None = None,
) -> AgentExecutor:
    tasks = AgentTaskRegistry()
    tasks.register(idea_curation_task(settings.ai_max_input_chars, settings.ai_timeout_seconds))
    for task in extensions.agent_task_specs():
        tasks.register(task)
    return AgentExecutor(
        create_model_provider(settings),
        tasks,
        build_core_tool_registry(vault, fixed_snapshot_id),
    )
