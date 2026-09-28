"""Load and validate effective Core and extension schedules."""

from __future__ import annotations

from .atomic import write_text
from .config import Settings
from .extensions import CORE_OPERATIONS, ExtensionRegistry
from .runtime import OperationRegistry, OperationRegistryError
from .schedule_models import ScheduleConfig, ScheduleDefinition, ScheduleOverride, ScheduleOverrides


DEFAULT_SCHEDULES = ScheduleConfig.model_validate(
    {
        "version": 1,
        "schedules": [
            {
                "schedule_id": "vault-content",
                "cron": "0 */6 * * *",
                "request": {"operation": "vault.content.refresh", "input": {}, "context": {}},
            },
            {
                "schedule_id": "idea-curate",
                "cron": "15 */6 * * *",
                "enabled": False,
                "request": {"operation": "ideas.curate", "input": {}, "context": {}},
            },
            {
                "schedule_id": "vault-audit",
                "cron": "30 4 * * *",
                "request": {"operation": "vault.audit", "input": {}, "context": {}},
            },
        ],
    }
)


class ScheduleConfigLoader:
    def __init__(
        self,
        settings: Settings,
        extensions: ExtensionRegistry,
        operation_registry: OperationRegistry,
    ) -> None:
        self.settings = settings
        self.extensions = extensions
        self.operation_registry = operation_registry

    def load(self) -> tuple[ScheduleConfig, dict[str, str]]:
        definitions = self._core_definitions()
        sources = {item.schedule_id: "core" for item in definitions}
        self._add_extension_definitions(definitions, sources)
        effective = self._apply_overrides(definitions)
        self._validate_operations(effective)
        enabled = [
            definition.model_copy(update={"enabled": False})
            if not self.operation_registry.availability(
                self.operation_registry.get(definition.request.operation)
            ).enabled
            else definition
            for definition in effective
        ]
        return ScheduleConfig(version=1, schedules=enabled), sources

    def _core_definitions(self) -> list[ScheduleDefinition]:
        path = self.settings.resolved_schedules_path
        external = self.settings.schedules_path is not None
        if not path.is_file():
            if external:
                raise ValueError(f"mounted Scheduler config is missing: {path}")
            write_text(path, DEFAULT_SCHEDULES.model_dump_json(indent=2))
            config = DEFAULT_SCHEDULES.model_copy(deep=True)
        else:
            config = ScheduleConfig.model_validate_json(path.read_text(encoding="utf-8"))

        existing_ids = {item.schedule_id for item in config.schedules}
        missing = [
            item.model_copy(deep=True)
            for item in DEFAULT_SCHEDULES.schedules
            if item.schedule_id not in existing_ids
        ]
        if missing:
            config = ScheduleConfig(version=1, schedules=config.schedules + missing)
            if not external:
                write_text(path, config.model_dump_json(indent=2))
        for definition in config.schedules:
            if definition.request.operation not in CORE_OPERATIONS:
                raise ValueError(
                    f"Core schedule cannot reference an extension operation: {definition.request.operation}"
                )
        return list(config.schedules)

    def _add_extension_definitions(
        self,
        definitions: list[ScheduleDefinition],
        sources: dict[str, str],
    ) -> None:
        for source, payload in self.extensions.schedule_payloads():
            definition = ScheduleDefinition.model_validate(payload)
            extension_id = source.removeprefix("extension:")
            if not definition.schedule_id.startswith(extension_id + "."):
                raise ValueError(
                    f"extension schedule must use the {extension_id}. prefix: {definition.schedule_id}"
                )
            if definition.schedule_id in sources:
                raise ValueError(f"duplicate effective schedule ID: {definition.schedule_id}")
            definitions.append(definition)
            sources[definition.schedule_id] = source

    def _apply_overrides(self, definitions: list[ScheduleDefinition]) -> list[ScheduleDefinition]:
        path = self.settings.resolved_schedule_overrides_path
        external = self.settings.schedule_overrides_path is not None
        if not path.is_file():
            if external:
                raise ValueError(f"mounted Scheduler override config is missing: {path}")
            overrides = ScheduleOverrides()
            write_text(path, overrides.model_dump_json(indent=2))
        else:
            overrides = ScheduleOverrides.model_validate_json(path.read_text(encoding="utf-8"))

        overrides_by_id = {item.schedule_id: item for item in overrides.overrides}
        return [self._apply_override(item, overrides_by_id.get(item.schedule_id)) for item in definitions]

    @staticmethod
    def _apply_override(
        definition: ScheduleDefinition,
        override: ScheduleOverride | None,
    ) -> ScheduleDefinition:
        if override is None:
            return definition
        changes = {
            key: value
            for key, value in override.model_dump(exclude={"schedule_id"}, exclude_unset=True).items()
            if value is not None
        }
        return definition.model_copy(update=changes)

    def _validate_operations(self, definitions: list[ScheduleDefinition]) -> None:
        for definition in definitions:
            try:
                operation = self.operation_registry.get(definition.request.operation)
            except OperationRegistryError as error:
                raise ValueError(f"scheduled operation is not available: {definition.request.operation}") from error
            if "scheduler" not in operation.roles:
                raise ValueError(f"operation is not allowed for scheduler: {definition.request.operation}")
