"""Persistent, in-process cron scheduler for predefined APS operations."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .extensions import CORE_OPERATIONS, ExtensionRegistry
from .models import JobStatus
from .runner import JobRunner
from .runtime import OperationRegistry, OperationRegistryError
from .schedule_models import (
    CronExpression,
    ScheduleConfig,
    ScheduleDefinition,
    ScheduleOverride,
    ScheduleOverrides,
    ScheduleRuntime,
    SchedulerState,
    SchedulerStatus,
    ScheduleView,
)
from .store import JobStore


CORE_DEFAULT_SCHEDULES = ScheduleConfig.model_validate(
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

EMPTY_OVERRIDES = ScheduleOverrides()
LEGACY_EXTENSION_SCHEDULE_IDS = {
    "daily-briefing": "briefing.daily-refresh",
    "service-maintenance": "briefing.service-maintenance",
}


class Scheduler:
    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        runner: JobRunner,
        extensions: ExtensionRegistry,
        operations: OperationRegistry,
    ) -> None:
        self.settings = settings
        try:
            ZoneInfo(settings.scheduler_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown scheduler timezone: {settings.scheduler_timezone}") from error
        self.store = store
        self.runner = runner
        self.extensions = extensions
        self.operations = operations
        self.config_path = settings.resolved_schedules_path
        self.overrides_path = settings.resolved_schedule_overrides_path
        self.state_path = settings.data_path / "scheduler-state.json"
        self.config = self._load_config()
        self.state = self._load_state()
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="aps-scheduler", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def status(self) -> SchedulerStatus:
        with self._lock:
            views: list[ScheduleView] = []
            for item in self.config.schedules:
                availability = self.operations.availability(self.operations.get(item.request.operation))
                views.append(ScheduleView(
                    schedule_id=item.schedule_id,
                    source=self.schedule_sources[item.schedule_id],
                    cron=item.cron,
                    timezone=item.timezone or self.settings.scheduler_timezone,
                    enabled=item.enabled,
                    disabled_reason=availability.reason,
                    request=item.request.model_dump(mode="json"),
                    runtime=self.state.schedules.get(item.schedule_id, ScheduleRuntime()),
                ))
            return SchedulerStatus(
                enabled=self.settings.scheduler_enabled,
                running=self._thread is not None and self._thread.is_alive(),
                last_tick_at=self.state.last_tick_at,
                queue=self.runner.status(),
                schedules=views,
            )

    def tick(self, now: datetime | None = None) -> None:
        current = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
        with self._lock:
            for job_id in self.store.queued_job_ids():
                try:
                    self.runner.submit(job_id)
                except RuntimeError:
                    break
            for definition in self.config.schedules:
                runtime = self.state.schedules.setdefault(definition.schedule_id, ScheduleRuntime())
                if definition.enabled:
                    try:
                        due = self._latest_due(definition, runtime.last_checked_at, current)
                        if due is not None:
                            self._enqueue(definition, runtime, due)
                        runtime.last_error = None
                    except Exception as error:  # Keep one invalid or full schedule from stopping the loop.
                        runtime.last_error = str(error)
                runtime.last_checked_at = current
            self.state.last_tick_at = current
            self._save_state()

    def _loop(self) -> None:
        self.tick()
        while not self._stopping.wait(self.settings.scheduler_poll_seconds):
            self.tick()

    def _latest_due(
        self,
        definition: ScheduleDefinition,
        last_checked_at: datetime | None,
        current: datetime,
    ) -> datetime | None:
        expression = CronExpression(definition.cron)
        timezone = ZoneInfo(definition.timezone or self.settings.scheduler_timezone)
        if last_checked_at is None:
            candidate = current
        else:
            earliest = current - timedelta(minutes=self.settings.scheduler_misfire_lookback_minutes - 1)
            candidate = max(last_checked_at.astimezone(UTC) + timedelta(minutes=1), earliest)
        latest: datetime | None = None
        while candidate <= current:
            if expression.matches(candidate.astimezone(timezone)):
                latest = candidate
            candidate += timedelta(minutes=1)
        return latest

    def _enqueue(self, definition: ScheduleDefinition, runtime: ScheduleRuntime, scheduled_for: datetime) -> None:
        availability = self.operations.availability(self.operations.get(definition.request.operation))
        if not availability.enabled:
            return
        key = f"schedule:{definition.schedule_id}:{scheduled_for.isoformat()}"
        existing = self.store.find_by_idempotency("scheduler", key)
        if existing is not None:
            if existing.request != definition.request:
                raise RuntimeError("scheduled idempotency key belongs to a different request")
            if existing.public.status == JobStatus.QUEUED:
                self.runner.submit(existing.public.job_id)
            runtime.last_scheduled_for = scheduled_for
            runtime.last_job_id = existing.public.job_id
            return
        stored = self.store.create(definition.request, "scheduler", datetime.now(UTC), key)
        self.runner.submit(stored.public.job_id)
        runtime.last_scheduled_for = scheduled_for
        runtime.last_job_id = stored.public.job_id

    def _load_config(self) -> ScheduleConfig:
        external_core_config = self.settings.schedules_path is not None
        external_overrides = self.settings.schedule_overrides_path is not None
        migrated_overrides: list[ScheduleOverride] = []
        if not self.config_path.is_file():
            if external_core_config:
                raise ValueError(f"mounted Scheduler config is missing: {self.config_path}")
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.config_path, CORE_DEFAULT_SCHEDULES.model_dump_json(indent=2))
            core_config = CORE_DEFAULT_SCHEDULES.model_copy(deep=True)
        else:
            core_config = ScheduleConfig.model_validate_json(self.config_path.read_text(encoding="utf-8"))
            retained: list[ScheduleDefinition] = []
            for definition in core_config.schedules:
                migrated_id = LEGACY_EXTENSION_SCHEDULE_IDS.get(definition.schedule_id)
                if migrated_id is None:
                    retained.append(definition)
                else:
                    migrated_overrides.append(
                        ScheduleOverride(
                            schedule_id=migrated_id,
                            cron=definition.cron,
                            timezone=definition.timezone,
                            enabled=definition.enabled,
                        )
                    )
            if len(retained) != len(core_config.schedules):
                core_config = ScheduleConfig(version=1, schedules=retained)
                if not external_core_config:
                    self._atomic_write(self.config_path, core_config.model_dump_json(indent=2))

            existing_core_ids = {definition.schedule_id for definition in core_config.schedules}
            missing_defaults = [
                definition.model_copy(deep=True)
                for definition in CORE_DEFAULT_SCHEDULES.schedules
                if definition.schedule_id not in existing_core_ids
            ]
            if missing_defaults:
                core_config = ScheduleConfig(version=1, schedules=core_config.schedules + missing_defaults)
                if not external_core_config:
                    self._atomic_write(self.config_path, core_config.model_dump_json(indent=2))

        for definition in core_config.schedules:
            if definition.request.operation not in CORE_OPERATIONS:
                raise ValueError(f"Core schedule cannot reference an extension operation: {definition.request.operation}")

        definitions = list(core_config.schedules)
        sources = {item.schedule_id: "core" for item in definitions}
        for source, payload in self.extensions.schedule_payloads():
            definition = ScheduleDefinition.model_validate(payload)
            extension_id = source.split(":", 1)[1]
            if not definition.schedule_id.startswith(extension_id + "."):
                raise ValueError(f"extension schedule must use the {extension_id}. prefix: {definition.schedule_id}")
            if definition.schedule_id in sources:
                raise ValueError(f"duplicate effective schedule ID: {definition.schedule_id}")
            definitions.append(definition)
            sources[definition.schedule_id] = source

        if not self.overrides_path.is_file():
            if external_overrides:
                raise ValueError(f"mounted Scheduler override config is missing: {self.overrides_path}")
            self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.overrides_path, EMPTY_OVERRIDES.model_dump_json(indent=2))
            overrides = EMPTY_OVERRIDES
        else:
            overrides = ScheduleOverrides.model_validate_json(self.overrides_path.read_text(encoding="utf-8"))
        if migrated_overrides:
            existing_override_ids = {item.schedule_id for item in overrides.overrides}
            overrides = ScheduleOverrides(
                version=1,
                overrides=overrides.overrides
                + [item for item in migrated_overrides if item.schedule_id not in existing_override_ids],
            )
            if not external_overrides:
                self._atomic_write(self.overrides_path, overrides.model_dump_json(indent=2, exclude_none=True))
        overrides_by_id = {item.schedule_id: item for item in overrides.overrides}
        effective: list[ScheduleDefinition] = []
        for definition in definitions:
            override = overrides_by_id.get(definition.schedule_id)
            if override is not None:
                changes = {
                    key: value
                    for key, value in override.model_dump(exclude={"schedule_id"}, exclude_unset=True).items()
                    if value is not None
                }
                definition = definition.model_copy(update=changes)
            effective.append(definition)

        config = ScheduleConfig(version=1, schedules=effective)
        for definition in config.schedules:
            try:
                operation = self.operations.get(definition.request.operation)
            except OperationRegistryError as error:
                raise ValueError(f"scheduled operation is not available: {definition.request.operation}") from error
            if "scheduler" not in operation.roles:
                raise ValueError(f"operation is not allowed for scheduler: {definition.request.operation}")
        config = ScheduleConfig(
            version=1,
            schedules=[
                definition.model_copy(update={"enabled": False})
                if not self.operations.availability(self.operations.get(definition.request.operation)).enabled
                else definition
                for definition in config.schedules
            ],
        )
        self.schedule_sources = sources
        return config

    def _load_state(self) -> SchedulerState:
        if not self.state_path.is_file():
            return SchedulerState()
        return SchedulerState.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.state_path, self.state.model_dump_json(indent=2))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
