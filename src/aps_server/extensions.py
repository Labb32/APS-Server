"""Discovery and installation of bundled, official APS extensions only."""

from __future__ import annotations

import re
import secrets
import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CreateJobRequest, OperationName


CORE_OPERATIONS = {
    OperationName.VAULT_AUDIT,
    OperationName.VAULT_CONTENT_REFRESH,
    OperationName.IDEAS_INDEX_REFRESH,
    OperationName.IDEAS_CURATE,
}


class ExtensionSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,127}$")
    cron: str = Field(min_length=1, max_length=128)
    timezone: str | None = None
    enabled: bool = True
    request: CreateJobRequest


class ExtensionAgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")
    mode: Literal["workflow", "tool-loop"] = "workflow"
    contract_module: str
    contract_model: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
    prompt_file: str
    allowed_tools: list[str] = Field(default_factory=list, max_length=20)
    tool_capabilities: list[str] = Field(default_factory=list, max_length=20)
    max_steps: int = Field(default=1, ge=1, le=8)
    max_input_chars: int = Field(default=200_000, ge=1000, le=2_000_000)
    max_output_chars: int = Field(default=200_000, ge=1000, le=2_000_000)
    timeout_seconds: int = Field(default=600, ge=10, le=7200)

    @field_validator("contract_module", "prompt_file")
    @classmethod
    def package_local_file(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("extension task files must be package-local paths")
        return path.as_posix()

    @field_validator("allowed_tools", "tool_capabilities")
    @classmethod
    def unique_identifiers(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("extension task identifiers must be unique")
        if any(not re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", value) for value in values):
            raise ValueError("extension task identifiers are invalid")
        return values


class ExtensionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    type: Literal["content-provider"]
    official: Literal[True]
    aps_api: Literal["1"]
    entrypoint: str
    resources: list[str] = Field(default_factory=list, max_length=100)
    capabilities: list[str]
    operations: list[OperationName]
    schedules: list[ExtensionSchedule] = Field(default_factory=list)
    agent_tasks: list[ExtensionAgentTask] = Field(default_factory=list)
    vault_access: Literal["read-only"]
    network: Literal["none", "ai-provider-only"]
    activation: Literal["restart"]

    @field_validator("entrypoint")
    @classmethod
    def safe_entrypoint(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or len(path.parts) != 1 or value in {".", ".."}:
            raise ValueError("entrypoint must be one package-local filename")
        return value

    @field_validator("resources")
    @classmethod
    def safe_resources(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("extension resources must be unique")
        for value in values:
            path = Path(value)
            if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
                raise ValueError("extension resources must be package-local paths")
        return values

    @field_validator("operations")
    @classmethod
    def unique_operations(cls, values: list[OperationName]) -> list[OperationName]:
        if len(values) != len(set(values)):
            raise ValueError("extension operations must be unique")
        return values

    @field_validator("schedules")
    @classmethod
    def unique_schedules(cls, values: list[ExtensionSchedule]) -> list[ExtensionSchedule]:
        identifiers = [item.schedule_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("extension schedule IDs must be unique")
        return values

    @field_validator("agent_tasks")
    @classmethod
    def unique_agent_tasks(cls, values: list[ExtensionAgentTask]) -> list[ExtensionAgentTask]:
        identifiers = [item.task_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("extension Agent task IDs must be unique")
        return values


class ExtensionInfo(BaseModel):
    extension_id: str
    version: str
    installed: bool
    active: bool
    operations: list[OperationName]
    schedules: list[str]
    restart_required: bool = False


class ExtensionListResponse(BaseModel):
    extensions: list[ExtensionInfo]


def load_manifest(package_root: Path, expected_id: str | None = None) -> ExtensionManifest:
    manifest_path = package_root / "manifest.json"
    manifest = ExtensionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.id != (expected_id or package_root.name):
        raise ValueError(f"manifest id does not match directory: {package_root.name}")
    entrypoint = (package_root / manifest.entrypoint).resolve()
    try:
        entrypoint.relative_to(package_root.resolve())
    except ValueError as error:
        raise ValueError("extension entrypoint escapes its package") from error
    if not entrypoint.is_file():
        raise ValueError(f"extension entrypoint is missing: {manifest.entrypoint}")
    for relative in manifest.resources:
        resource = (package_root / relative).resolve()
        try:
            resource.relative_to(package_root.resolve())
        except ValueError as error:
            raise ValueError(f"extension resource escapes its package: {relative}") from error
        if not resource.is_file():
            raise ValueError(f"extension resource is missing: {relative}")
    for schedule in manifest.schedules:
        if not schedule.schedule_id.startswith(manifest.id + "."):
            raise ValueError(f"extension schedule must use the {manifest.id}. prefix: {schedule.schedule_id}")
        if schedule.request.operation not in manifest.operations:
            raise ValueError(f"extension schedule references an unowned operation: {schedule.request.operation}")
    for task in manifest.agent_tasks:
        if not task.task_id.startswith(manifest.id + "."):
            raise ValueError(f"extension Agent task must use the {manifest.id}. prefix: {task.task_id}")
        for relative in (task.contract_module, task.prompt_file):
            target = (package_root / relative).resolve()
            try:
                target.relative_to(package_root.resolve())
            except ValueError as error:
                raise ValueError(f"extension Agent task file escapes its package: {relative}") from error
            if not target.is_file():
                raise ValueError(f"extension Agent task file is missing: {relative}")
    return manifest


class ExtensionRegistry:
    """Validated extensions that are active for this server process."""

    def __init__(self, installed_root: Path) -> None:
        self.installed_root = installed_root
        self.installed_root.mkdir(parents=True, exist_ok=True)
        self.manifests: dict[str, ExtensionManifest] = {}
        operation_owners: dict[OperationName, str] = {}
        for package_root in sorted(
            path for path in installed_root.iterdir() if path.is_dir() and not path.name.startswith(".")
        ):
            manifest = load_manifest(package_root)
            for operation in manifest.operations:
                if operation in CORE_OPERATIONS:
                    raise ValueError(f"extension cannot replace Core operation: {operation}")
                owner = operation_owners.get(operation)
                if owner is not None:
                    raise ValueError(f"operation is provided by both {owner} and {manifest.id}: {operation}")
                operation_owners[operation] = manifest.id
            self.manifests[manifest.id] = manifest
        self.operation_owners = operation_owners

    @property
    def available_operations(self) -> set[OperationName]:
        return CORE_OPERATIONS | set(self.operation_owners)

    def is_installed(self, extension_id: str) -> bool:
        return extension_id in self.manifests

    def agent_task_specs(self) -> list[Any]:
        import importlib.util
        import sys

        from pydantic import BaseModel

        from .agent import AgentTaskSpec

        specs: list[AgentTaskSpec] = []
        seen: set[str] = set()
        for extension_id, manifest in self.manifests.items():
            package_root = self.installed_root / extension_id
            for task in manifest.agent_tasks:
                if task.task_id in seen:
                    raise ValueError(f"duplicate extension Agent task: {task.task_id}")
                module_path = package_root / task.contract_module
                module_name = "aps_extension_" + task.task_id.replace(".", "_").replace("-", "_")
                module_spec = importlib.util.spec_from_file_location(module_name, module_path)
                if module_spec is None or module_spec.loader is None:
                    raise ValueError(f"cannot load extension task contract: {task.task_id}")
                module = importlib.util.module_from_spec(module_spec)
                sys.modules[module_name] = module
                module_spec.loader.exec_module(module)
                output_model = getattr(module, task.contract_model, None)
                if not isinstance(output_model, type) or not issubclass(output_model, BaseModel):
                    raise ValueError(f"extension task contract is not a Pydantic model: {task.task_id}")
                instructions = (package_root / task.prompt_file).read_text(encoding="utf-8-sig")
                specs.append(
                    AgentTaskSpec(
                        task_id=task.task_id,
                        mode=task.mode,
                        instructions=instructions,
                        output_model=output_model,
                        allowed_tools=frozenset(task.allowed_tools),
                        max_steps=task.max_steps,
                        max_input_chars=task.max_input_chars,
                        max_output_chars=task.max_output_chars,
                        timeout_seconds=task.timeout_seconds,
                    )
                )
                seen.add(task.task_id)
        return specs

    def agent_task_capabilities(self, task_id: str) -> frozenset[str]:
        for manifest in self.manifests.values():
            for task in manifest.agent_tasks:
                if task.task_id == task_id:
                    return frozenset(task.tool_capabilities)
        return frozenset()

    def schedule_payloads(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (f"extension:{manifest.id}", schedule.model_dump(mode="json"))
            for manifest in self.manifests.values()
            for schedule in manifest.schedules
        ]

    def active_info(self) -> list[ExtensionInfo]:
        return [
            ExtensionInfo(
                extension_id=manifest.id,
                version=manifest.version,
                installed=True,
                active=True,
                operations=manifest.operations,
                schedules=[item.schedule_id for item in manifest.schedules],
            )
            for manifest in self.manifests.values()
        ]


class OfficialExtensionInstaller:
    """Installs only packages shipped in the APS official package directory."""

    def __init__(self, official_root: Path, installed_root: Path) -> None:
        self.official_root = official_root.resolve()
        self.installed_root = installed_root.resolve()
        self.installed_root.mkdir(parents=True, exist_ok=True)

    def list(self) -> ExtensionListResponse:
        installed = {
            path.name: load_manifest(path)
            for path in self.installed_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        }
        result: list[ExtensionInfo] = []
        if self.official_root.is_dir():
            for source in sorted(path for path in self.official_root.iterdir() if path.is_dir()):
                manifest = load_manifest(source)
                current = installed.get(manifest.id)
                result.append(
                    ExtensionInfo(
                        extension_id=manifest.id,
                        version=manifest.version,
                        installed=current is not None,
                        active=current is not None,
                        operations=manifest.operations,
                        schedules=[item.schedule_id for item in manifest.schedules],
                    )
                )
        return ExtensionListResponse(extensions=result)

    def install(self, extension_id: str) -> ExtensionInfo:
        if not extension_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in extension_id):
            raise ValueError("invalid official extension id")
        source = (self.official_root / extension_id).resolve()
        try:
            source.relative_to(self.official_root)
        except ValueError as error:
            raise ValueError("official extension path is invalid") from error
        if not source.is_dir():
            raise KeyError(extension_id)
        manifest = load_manifest(source)
        target = (self.installed_root / extension_id).resolve()
        try:
            target.relative_to(self.installed_root)
        except ValueError as error:
            raise ValueError("installed extension path is invalid") from error
        if target.exists():
            current = load_manifest(target)
            if current.version == manifest.version:
                return ExtensionInfo(
                    extension_id=current.id,
                    version=current.version,
                    installed=True,
                    active=True,
                    operations=current.operations,
                    schedules=[item.schedule_id for item in current.schedules],
                    restart_required=False,
                )
        temporary = self.installed_root / f".{extension_id}-{secrets.token_hex(6)}.tmp"
        backup = self.installed_root / f".{extension_id}-{secrets.token_hex(6)}.bak"
        try:
            shutil.copytree(source, temporary)
            load_manifest(temporary, expected_id=extension_id)
            if target.exists():
                target.replace(backup)
            temporary.replace(target)
        except Exception:
            if temporary.is_dir():
                shutil.rmtree(temporary)
            if backup.is_dir() and not target.exists():
                backup.replace(target)
            raise
        finally:
            if backup.is_dir():
                shutil.rmtree(backup)
        return ExtensionInfo(
            extension_id=manifest.id,
            version=manifest.version,
            installed=True,
            active=False,
            operations=manifest.operations,
            schedules=[item.schedule_id for item in manifest.schedules],
            restart_required=True,
        )
