"""Persistent, in-process cron scheduler for predefined APS operations."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .atomic import write_text
from .config import Settings
from .extensions import ExtensionRegistry
from .external_scheduler import ExternalSchedulerCLI
from .models import JobStatus
from .runner import JobRunner
from .runtime import OperationRegistry
from .schedule_config import ScheduleConfigLoader
from .schedule_models import (
    CronExpression,
    ScheduleDefinition,
    ScheduleRuntime,
    SchedulerState,
    SchedulerStatus,
    ScheduleView,
)
from .store import JobStore


class Scheduler:
    def __init__(
        self,
        settings: Settings,
        job_store: JobStore,
        job_runner: JobRunner,
        extensions: ExtensionRegistry,
        operation_registry: OperationRegistry,
    ) -> None:
        self.settings = settings
        try:
            ZoneInfo(settings.scheduler_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown scheduler timezone: {settings.scheduler_timezone}") from error
        self.job_store = job_store
        self.job_runner = job_runner
        self.operation_registry = operation_registry
        self.state_path = settings.data_path / "scheduler-state.json"
        self.schedule_config, self.schedule_sources = ScheduleConfigLoader(
            settings,
            extensions,
            operation_registry,
        ).load()
        self.runtime_state = self._load_state()
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._external_synced_at: datetime | None = None
        self._external_error: str | None = None
        self._external_attempted = False

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self._thread is not None or self._external_attempted:
            return
        if self.settings.scheduler_backend == "external-cli":
            self._external_attempted = True
            try:
                cli_path = self.settings.external_scheduler_cli
                if cli_path is None:
                    raise ValueError("external Scheduler CLI is not configured")
                self._external_synced_at = ExternalSchedulerCLI(
                    cli_path,
                    self.settings.data_path,
                    self.settings.external_scheduler_timeout_seconds,
                ).apply(self.schedule_config.schedules, self.settings.scheduler_timezone)
                self._external_error = None
            except Exception as error:
                self._external_error = str(error)
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
            for item in self.schedule_config.schedules:
                availability = self.operation_registry.availability(
                    self.operation_registry.get(item.request.operation)
                )
                views.append(ScheduleView(
                    schedule_id=item.schedule_id,
                    source=self.schedule_sources[item.schedule_id],
                    cron=item.cron,
                    timezone=item.timezone or self.settings.scheduler_timezone,
                    enabled=item.enabled,
                    disabled_reason=availability.reason,
                    request=item.request.model_dump(mode="json"),
                    runtime=self.runtime_state.schedules.get(item.schedule_id, ScheduleRuntime()),
                ))
            return SchedulerStatus(
                enabled=self.settings.scheduler_enabled,
                running=(
                    self._external_error is None and self._external_synced_at is not None
                    if self.settings.scheduler_backend == "external-cli"
                    else self._thread is not None and self._thread.is_alive()
                ),
                backend=self.settings.scheduler_backend,
                external_synced_at=self._external_synced_at,
                external_error=self._external_error,
                last_tick_at=self.runtime_state.last_tick_at,
                queue=self.job_runner.status(),
                schedules=views,
            )

    def tick(self, now: datetime | None = None) -> None:
        current = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
        with self._lock:
            for job_id in self.job_store.queued_job_ids():
                try:
                    self.job_runner.submit(job_id)
                except RuntimeError:
                    break
            for definition in self.schedule_config.schedules:
                runtime = self.runtime_state.schedules.setdefault(definition.schedule_id, ScheduleRuntime())
                if definition.enabled:
                    try:
                        due = self._latest_due(definition, runtime.last_checked_at, current)
                        if due is not None:
                            self._enqueue(definition, runtime, due)
                        runtime.last_error = None
                    except Exception as error:  # Keep one invalid or full schedule from stopping the loop.
                        runtime.last_error = str(error)
                runtime.last_checked_at = current
            self.runtime_state.last_tick_at = current
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
        availability = self.operation_registry.availability(
            self.operation_registry.get(definition.request.operation)
        )
        if not availability.enabled:
            return
        key = f"schedule:{definition.schedule_id}:{scheduled_for.isoformat()}"
        existing = self.job_store.find_by_idempotency("scheduler", key)
        if existing is not None:
            if existing.request != definition.request:
                raise RuntimeError("scheduled idempotency key belongs to a different request")
            if existing.public.status == JobStatus.QUEUED:
                self.job_runner.submit(existing.public.job_id)
            runtime.last_scheduled_for = scheduled_for
            runtime.last_job_id = existing.public.job_id
            return
        stored = self.job_store.create(definition.request, "scheduler", datetime.now(UTC), key)
        self.job_runner.submit(stored.public.job_id)
        runtime.last_scheduled_for = scheduled_for
        runtime.last_job_id = stored.public.job_id

    def _load_state(self) -> SchedulerState:
        if not self.state_path.is_file():
            return SchedulerState()
        return SchedulerState.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self) -> None:
        write_text(self.state_path, self.runtime_state.model_dump_json(indent=2))
