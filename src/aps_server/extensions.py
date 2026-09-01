"""Discovery and installation of bundled, official APS extensions only."""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CreateJobRequest, OperationName


CORE_OPERATIONS = {
    OperationName.VAULT_AUDIT,
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


class ExtensionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    type: Literal["content-provider"]
    official: Literal[True]
    aps_api: Literal["1"]
    entrypoint: str
    capabilities: list[str]
    operations: list[OperationName]
    schedules: list[ExtensionSchedule] = Field(default_factory=list)
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
    for schedule in manifest.schedules:
        if not schedule.schedule_id.startswith(manifest.id + "."):
            raise ValueError(f"extension schedule must use the {manifest.id}. prefix: {schedule.schedule_id}")
        if schedule.request.operation not in manifest.operations:
            raise ValueError(f"extension schedule references an unowned operation: {schedule.request.operation}")
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
        try:
            shutil.copytree(source, temporary)
            load_manifest(temporary, expected_id=extension_id)
            temporary.replace(target)
        except Exception:
            if temporary.is_dir():
                shutil.rmtree(temporary)
            raise
        return ExtensionInfo(
            extension_id=manifest.id,
            version=manifest.version,
            installed=True,
            active=False,
            operations=manifest.operations,
            schedules=[item.schedule_id for item in manifest.schedules],
            restart_required=True,
        )
