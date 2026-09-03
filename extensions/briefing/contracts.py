"""Structured Agent contracts owned by the official briefing extension."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BriefingAIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    today_tasks: list[str] = Field(max_length=3)
    notes: list[str] = Field(max_length=2)

    @field_validator("today_tasks", "notes")
    @classmethod
    def normalize_items(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]
