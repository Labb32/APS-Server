from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APS_", env_file=".env", extra="ignore")

    vault_path: Path = Path("vault")
    vault_mode: Literal["local", "git", "mounted"] = "local"
    vault_git_url: str | None = None
    vault_git_branch: str | None = None
    vault_template_path: Path = Path("/opt/aps/vault-template")
    data_path: Path = Path("data")
    extensions_path: Path = Path("data/extensions")
    official_extensions_path: Path = Path("extensions")
    initial_extensions: str = ""
    index_url: AnyHttpUrl | None = None
    config_file: Path | None = None
    http_host: str = "0.0.0.0"
    http_port: int = Field(default=8080, ge=1, le=65535)
    operator_token: str = Field(default="", min_length=0)
    viewer_token: str = Field(default="", min_length=0)
    scheduler_token: str = Field(default="", min_length=0)
    sync_before_job: bool = True
    job_workers: int = Field(default=2, ge=1, le=8)
    job_queue_size: int = Field(default=100, ge=1, le=10000)
    job_timeout_seconds: int = Field(default=900, ge=30, le=7200)
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Seoul"
    scheduler_poll_seconds: int = Field(default=30, ge=1, le=300)
    scheduler_misfire_lookback_minutes: int = Field(default=1440, ge=1, le=10080)
    schedules_path: Path | None = None
    schedule_overrides_path: Path | None = None

    @property
    def resolved_schedules_path(self) -> Path:
        return self.schedules_path or self.data_path / "schedules.json"

    @property
    def resolved_schedule_overrides_path(self) -> Path:
        return self.schedule_overrides_path or self.data_path / "schedule-overrides.json"

    @property
    def requested_extensions(self) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in self.initial_extensions.split(",") if item.strip()))

    @property
    def tokens(self) -> dict[str, str]:
        return {
            token: role
            for token, role in (
                (self.operator_token, "operator"),
                (self.viewer_token, "viewer"),
                (self.scheduler_token, "scheduler"),
            )
            if token
        }

    @property
    def configured(self) -> bool:
        return self.vault_path.is_dir() and bool(self.tokens)
