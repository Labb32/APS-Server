"""Core-owned AI provider selection and structured response validation.

Provider configuration is process configuration, never requester input.  Every
adapter receives the same prompt and must return the same validated model so an
official extension does not depend on a vendor-specific response shape.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import Settings


MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024


class AIGatewayError(RuntimeError):
    pass


class BriefingAIResponse(BaseModel):
    """Provider-neutral output consumed by the official briefing extension."""

    model_config = ConfigDict(extra="forbid")

    today_tasks: list[str] = Field(max_length=3)
    notes: list[str] = Field(max_length=2)

    @field_validator("today_tasks", "notes")
    @classmethod
    def normalize_items(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


SCHEMAS: dict[str, type[BaseModel]] = {"briefing": BriefingAIResponse}


class AIGateway:
    """Dispatch a fixed structured task to the configured server-side provider."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def readiness(self) -> tuple[bool, dict[str, Any]]:
        provider = self.settings.ai_provider
        configured = True
        if provider == "codex":
            executable = "codex.cmd" if os.name == "nt" else "codex"
            configured = shutil.which(executable) is not None
        elif provider == "openai-compatible":
            configured = bool(self.settings.ai_base_url and self.settings.ai_model.strip())
        elif provider == "agent-http":
            configured = self.settings.ai_base_url is not None
        return configured, {
            "provider": provider,
            "configured": configured,
            "model": self.settings.ai_model or None,
            "endpoint_configured": self.settings.ai_base_url is not None,
        }

    def generate(self, schema_id: str, prompt: str) -> BaseModel:
        if schema_id not in SCHEMAS:
            raise AIGatewayError(f"unsupported AI response schema: {schema_id}")
        configured, _ = self.readiness()
        if not configured:
            raise AIGatewayError(f"AI provider is not configured: {self.settings.ai_provider}")
        if not prompt.strip():
            raise AIGatewayError("AI prompt is empty")
        if len(prompt) > self.settings.ai_max_input_chars:
            raise AIGatewayError("AI prompt exceeds the configured input limit")

        schema_model = SCHEMAS[schema_id]
        schema = schema_model.model_json_schema()
        if self.settings.ai_provider == "codex":
            raw = self._codex(prompt, schema)
        elif self.settings.ai_provider == "openai-compatible":
            raw = self._openai_compatible(prompt, schema_id, schema)
        elif self.settings.ai_provider == "agent-http":
            raw = self._agent_http(prompt, schema_id, schema)
        else:  # Settings validation normally makes this unreachable.
            raise AIGatewayError(f"unsupported AI provider: {self.settings.ai_provider}")
        try:
            return schema_model.model_validate(raw)
        except ValidationError as error:
            # Do not copy model output into Job errors or logs.
            raise AIGatewayError(f"AI provider returned invalid {schema_id} output") from error

    def _codex(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        executable = "codex.cmd" if os.name == "nt" else "codex"
        if shutil.which(executable) is None:
            raise AIGatewayError("Codex CLI is not installed")
        with tempfile.TemporaryDirectory(prefix="aps-ai-") as temporary:
            schema_path = Path(temporary) / "response.schema.json"
            schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            try:
                completed = subprocess.run(
                    [
                        executable, "exec", "--ephemeral", "--sandbox", "read-only",
                        "--output-schema", str(schema_path), "-",
                    ],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.settings.ai_timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise AIGatewayError(f"Codex execution failed: {error}") from error
        if completed.returncode:
            raise AIGatewayError(f"Codex execution failed with exit code {completed.returncode}")
        return self._json_object(completed.stdout, "Codex")

    def _openai_compatible(self, prompt: str, schema_id: str, schema: dict[str, Any]) -> dict[str, Any]:
        endpoint = self._required_endpoint(append="chat/completions")
        system_message = "Return only JSON that satisfies the requested response schema."
        if not self.settings.ai_structured_output:
            system_message += " JSON Schema: " + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        request_body: dict[str, Any] = {
            "model": self.settings.ai_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_message,
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        if self.settings.ai_structured_output:
            request_body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": f"aps_{schema_id}", "strict": True, "schema": schema},
            }
        payload = self._post_json(endpoint, request_body)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise AIGatewayError("OpenAI-compatible response has no message content") from error
        if not isinstance(content, str):
            raise AIGatewayError("OpenAI-compatible message content must be a JSON string")
        return self._json_object(content, "OpenAI-compatible provider")

    def _agent_http(self, prompt: str, schema_id: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = self._post_json(
            self._required_endpoint(),
            {
                "contract_version": 1,
                "task": schema_id,
                "input": prompt,
                "response_schema": schema,
            },
        )
        output = payload.get("output")
        if not isinstance(output, dict):
            raise AIGatewayError("Agent HTTP response must contain an object in 'output'")
        return output

    def _required_endpoint(self, append: str | None = None) -> str:
        if self.settings.ai_base_url is None:
            raise AIGatewayError(f"APS_AI_BASE_URL is required for {self.settings.ai_provider}")
        endpoint = str(self.settings.ai_base_url).rstrip("/")
        if append and not endpoint.endswith(append):
            endpoint = f"{endpoint}/{append}"
        return endpoint

    def _post_json(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.ai_api_key:
            headers["Authorization"] = f"Bearer {self.settings.ai_api_key.get_secret_value()}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.ai_timeout_seconds) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise AIGatewayError(f"AI provider request failed with HTTP {error.code}") from error
        except (OSError, urllib.error.URLError) as error:
            raise AIGatewayError("AI provider request failed") from error
        if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
            raise AIGatewayError("AI provider response exceeds the size limit")
        return self._json_object(raw.decode("utf-8", errors="replace"), "AI provider")

    @staticmethod
    def _json_object(value: str, provider: str) -> dict[str, Any]:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise AIGatewayError(f"{provider} returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise AIGatewayError(f"{provider} JSON response must be an object")
        return payload
