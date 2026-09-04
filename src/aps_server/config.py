from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APS_", env_file=".env", extra="ignore")

    vault_path: Path = Path("vault")
    vault_mode: Literal["local", "git", "mounted"] = "local"
    vault_git_url: str | None = None
    vault_git_branch: str | None = None
    vault_push_after_commit: bool = False
    vault_template_path: Path = Path("/opt/aps/vault-template")
    data_path: Path = Path("data")
    extensions_path: Path = Path("data/extensions")
    official_extensions_path: Path = Path("extensions")
    initial_extensions: str = ""
    index_url: AnyHttpUrl | None = None
    ai_provider: Literal["openai", "openai-compatible", "agent-http"]
    ai_base_url: AnyHttpUrl | None = None
    ai_api_key: SecretStr | None = None
    ai_model: str = ""
    ai_timeout_seconds: int = Field(default=600, ge=10, le=7200)
    ai_parallel_requests: int = Field(default=3, ge=1, le=8)
    ai_max_input_chars: int = Field(default=200000, ge=1000, le=2000000)
    ai_structured_output: bool = True
    config_file: Path | None = None
    http_host: str = "0.0.0.0"
    http_port: int = Field(default=8080, ge=1, le=65535)
    operator_token: SecretStr | None = None
    viewer_token: SecretStr | None = None
    scheduler_token: SecretStr | None = None
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

    @field_validator("ai_base_url")
    @classmethod
    def reject_provider_url_credentials(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and (value.username or value.password):
            raise ValueError("APS_AI_BASE_URL must not contain credentials; use APS_AI_API_KEY")
        if value is not None and (value.query or value.fragment):
            raise ValueError("APS_AI_BASE_URL must not contain a query or fragment")
        return value

    @field_validator("vault_git_url")
    @classmethod
    def reject_git_url_credentials(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        if not candidate or candidate.startswith("-") or any(char in candidate for char in "\r\n\0"):
            raise ValueError("APS_VAULT_GIT_URL is invalid")
        parsed = urlsplit(candidate)
        if parsed.scheme in {"http", "https"} and (parsed.username or parsed.password):
            raise ValueError("APS_VAULT_GIT_URL must not contain credentials; use a credential mount")
        return candidate

    @field_validator("vault_git_branch")
    @classmethod
    def validate_git_branch(cls, value: str | None) -> str | None:
        if value is None:
            return None
        branch = value.strip()
        if not branch or branch.startswith("-") or any(char in branch for char in "\r\n\0"):
            raise ValueError("APS_VAULT_GIT_BRANCH is invalid")
        return branch

    @model_validator(mode="after")
    def require_selected_provider_configuration(self) -> "Settings":
        configured_tokens = [
            token.get_secret_value().strip()
            for token in (self.operator_token, self.viewer_token, self.scheduler_token)
            if token is not None and token.get_secret_value().strip()
        ]
        if any(len(token) < 32 for token in configured_tokens):
            raise ValueError("APS API tokens must contain at least 32 characters")
        if len(configured_tokens) != len(set(configured_tokens)):
            raise ValueError("APS API tokens must be distinct")
        if self.vault_push_after_commit and self.vault_mode == "local":
            raise ValueError("APS_VAULT_PUSH_AFTER_COMMIT requires git or mounted Vault mode")
        if self.ai_provider == "openai":
            if self.ai_api_key is None or not self.ai_api_key.get_secret_value().strip():
                raise ValueError("APS_AI_API_KEY is required when APS_AI_PROVIDER=openai")
            if not self.ai_model.strip():
                raise ValueError("APS_AI_MODEL is required when APS_AI_PROVIDER=openai")
        elif self.ai_provider == "openai-compatible":
            if self.ai_base_url is None:
                raise ValueError("APS_AI_BASE_URL is required when APS_AI_PROVIDER=openai-compatible")
            if not self.ai_model.strip():
                raise ValueError("APS_AI_MODEL is required when APS_AI_PROVIDER=openai-compatible")
        elif self.ai_provider == "agent-http" and self.ai_base_url is None:
            raise ValueError("APS_AI_BASE_URL is required when APS_AI_PROVIDER=agent-http")
        return self

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
                (self.operator_token.get_secret_value().strip() if self.operator_token else "", "operator"),
                (self.viewer_token.get_secret_value().strip() if self.viewer_token else "", "viewer"),
                (self.scheduler_token.get_secret_value().strip() if self.scheduler_token else "", "scheduler"),
            )
            if token
        }

    @property
    def configured(self) -> bool:
        return self.vault_path.is_dir() and bool(self.tokens)
