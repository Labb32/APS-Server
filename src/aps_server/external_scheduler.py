"""Restricted adapter for an external Scheduler CLI."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .atomic import write_text
from .schedule_models import ScheduleDefinition


class ExternalSchedulerError(RuntimeError):
    pass


class ExternalSchedulerCLI:
    """Publish APS schedules through one fixed, server-owned CLI contract."""

    def __init__(self, executable: Path, data_path: Path, timeout_seconds: int) -> None:
        self.executable = executable
        self.manifest_path = data_path / "scheduler" / "external-manifest.json"
        self.timeout_seconds = timeout_seconds

    def apply(self, schedules: list[ScheduleDefinition], default_timezone: str) -> datetime:
        if not self.executable.is_absolute():
            raise ExternalSchedulerError("external Scheduler CLI path must be absolute")
        executable = self.executable.resolve()
        if not executable.is_file():
            raise ExternalSchedulerError("external Scheduler CLI must be an existing absolute file")
        manifest = {
            "version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "schedules": [
                {
                    "schedule_id": item.schedule_id,
                    "cron": item.cron,
                    "timezone": item.timezone or default_timezone,
                    "enabled": item.enabled,
                    "command": [
                        "aps", "schedule-run", item.schedule_id,
                        "--scheduled-for", "{scheduled_for}",
                    ],
                }
                for item in schedules
            ],
        }
        write_text(self.manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        environment = {
            key: value
            for key in ("PATH", "HOME", "SYSTEMROOT", "TEMP", "TMP")
            if (value := os.environ.get(key))
        }
        try:
            completed = subprocess.run(
                [str(executable), "apply", "--manifest", str(self.manifest_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExternalSchedulerError("external Scheduler CLI could not apply the manifest") from error
        if completed.returncode != 0:
            raise ExternalSchedulerError("external Scheduler CLI rejected the manifest")
        return datetime.now(UTC)
