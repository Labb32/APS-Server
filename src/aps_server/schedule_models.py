"""Validated Scheduler configuration, runtime views, and cron matching.

Only numeric five-field cron is supported.  The intentionally small grammar is
part of the security boundary: configuration selects a registered Job model and
never embeds a command or executable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CreateJobRequest


class CronExpression:
    """Numeric, five-field cron expression with standard DOM/DOW semantics."""

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError("cron must contain minute hour day-of-month month day-of-week")
        self.minute, _ = self._field(fields[0], 0, 59)
        self.hour, _ = self._field(fields[1], 0, 23)
        self.day, self.day_all = self._field(fields[2], 1, 31)
        self.month, _ = self._field(fields[3], 1, 12)
        weekdays, self.weekday_all = self._field(fields[4], 0, 7)
        self.weekday = {0 if value == 7 else value for value in weekdays}

    @staticmethod
    def _field(text: str, minimum: int, maximum: int) -> tuple[set[int], bool]:
        values: set[int] = set()
        for part in text.split(","):
            if not part:
                raise ValueError("cron field contains an empty list item")
            base, separator, raw_step = part.partition("/")
            step = int(raw_step) if separator else 1
            if step < 1:
                raise ValueError("cron step must be positive")
            if base == "*":
                start, end = minimum, maximum
            elif "-" in base:
                raw_start, raw_end = base.split("-", 1)
                start, end = int(raw_start), int(raw_end)
            else:
                start = end = int(base)
            if start < minimum or end > maximum or start > end:
                raise ValueError(f"cron value must be between {minimum} and {maximum}")
            values.update(range(start, end + 1, step))
        return values, values == set(range(minimum, maximum + 1))

    def matches(self, value: datetime) -> bool:
        weekday = (value.weekday() + 1) % 7
        day_of_month = value.day in self.day
        day_of_week = weekday in self.weekday
        if self.day_all and self.weekday_all:
            day_matches = True
        elif self.day_all:
            day_matches = day_of_week
        elif self.weekday_all:
            day_matches = day_of_month
        else:
            day_matches = day_of_month or day_of_week
        return (
            value.minute in self.minute
            and value.hour in self.hour
            and value.month in self.month
            and day_matches
        )


def _validate_timezone(value: str | None) -> str | None:
    if value is not None:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {value}") from error
    return value


class ScheduleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,127}$")
    cron: str
    timezone: str | None = None
    enabled: bool = True
    request: CreateJobRequest

    @field_validator("cron")
    @classmethod
    def valid_cron(cls, value: str) -> str:
        CronExpression(value)
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1, le=1)
    schedules: list[ScheduleDefinition]

    @field_validator("schedules")
    @classmethod
    def unique_ids(cls, values: list[ScheduleDefinition]) -> list[ScheduleDefinition]:
        identifiers = [item.schedule_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("schedule_id values must be unique")
        return values


class ScheduleOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,127}$")
    cron: str | None = None
    timezone: str | None = None
    enabled: bool | None = None

    @field_validator("cron")
    @classmethod
    def valid_override_cron(cls, value: str | None) -> str | None:
        if value is not None:
            CronExpression(value)
        return value

    @field_validator("timezone")
    @classmethod
    def valid_override_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)


class ScheduleOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1, le=1)
    overrides: list[ScheduleOverride] = Field(default_factory=list)

    @field_validator("overrides")
    @classmethod
    def unique_ids(cls, values: list[ScheduleOverride]) -> list[ScheduleOverride]:
        identifiers = [item.schedule_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("schedule override IDs must be unique")
        return values


class ScheduleRuntime(BaseModel):
    last_checked_at: datetime | None = None
    last_scheduled_for: datetime | None = None
    last_job_id: str | None = None
    last_error: str | None = None


class SchedulerState(BaseModel):
    version: int = 1
    last_tick_at: datetime | None = None
    schedules: dict[str, ScheduleRuntime] = Field(default_factory=dict)


class ScheduleView(BaseModel):
    schedule_id: str
    source: str
    cron: str
    timezone: str
    enabled: bool
    request: dict[str, Any]
    runtime: ScheduleRuntime


class SchedulerStatus(BaseModel):
    enabled: bool
    running: bool
    last_tick_at: datetime | None
    queue: dict[str, int]
    schedules: list[ScheduleView]
