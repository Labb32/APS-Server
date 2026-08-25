from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APS_", env_file=".env", extra="ignore")

    vault_path: Path = Path("vault")
    data_path: Path = Path("data")
    operator_token: str = Field(default="", min_length=0)
    viewer_token: str = Field(default="", min_length=0)
    scheduler_token: str = Field(default="", min_length=0)
    sync_before_job: bool = True
    job_workers: int = Field(default=2, ge=1, le=8)
    job_timeout_seconds: int = Field(default=900, ge=30, le=7200)

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
