"""Model-only provider adapters used by the Core AgentExecutor."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from ..config import Settings
from .contracts import ModelRequest


MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024


class ModelProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "PROVIDER_FAILED") -> None:
        super().__init__(message)
        self.code = code


class ModelProvider(Protocol):
    provider_id: str

    def generate(self, request: ModelRequest, timeout_seconds: int) -> dict[str, Any]: ...


def provider_status(settings: Settings) -> tuple[bool, dict[str, Any]]:
    provider = settings.ai_provider
    configured = True
    if provider == "openai":
        configured = bool(
            settings.ai_api_key
            and settings.ai_api_key.get_secret_value().strip()
            and settings.ai_model.strip()
        )
    elif provider == "openai-compatible":
        configured = bool(settings.ai_base_url and settings.ai_model.strip())
    elif provider == "agent-http":
        configured = settings.ai_base_url is not None
    return configured, {
        "provider": provider,
        "configured": configured,
        "model": settings.ai_model or None,
        "endpoint_configured": provider == "openai" or settings.ai_base_url is not None,
    }


class _HTTPProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _post_json(self, endpoint: str, body: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
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
            timeout = min(timeout_seconds, self.settings.ai_timeout_seconds)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise ModelProviderError(
                f"model provider request failed with HTTP {error.code}",
                "PROVIDER_HTTP_ERROR",
            ) from error
        except (OSError, urllib.error.URLError) as error:
            raise ModelProviderError("model provider request failed", "PROVIDER_UNAVAILABLE") from error
        if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ModelProviderError("model provider response exceeds the size limit", "PROVIDER_OUTPUT_TOO_LARGE")
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as error:
            raise ModelProviderError("model provider returned invalid JSON", "PROVIDER_RESPONSE_INVALID") from error
        if not isinstance(payload, dict):
            raise ModelProviderError("model provider response must be a JSON object", "PROVIDER_RESPONSE_INVALID")
        return payload

    @staticmethod
    def _json_object(value: str, source: str) -> dict[str, Any]:
        try:
            result = json.loads(value)
        except json.JSONDecodeError as error:
            raise ModelProviderError(f"{source} returned invalid structured JSON", "PROVIDER_OUTPUT_INVALID") from error
        if not isinstance(result, dict):
            raise ModelProviderError(f"{source} output must be a JSON object", "PROVIDER_OUTPUT_INVALID")
        return result

    @staticmethod
    def _input_text(request: ModelRequest) -> str:
        return json.dumps(request.input, ensure_ascii=False, separators=(",", ":"))


class OpenAIResponsesProvider(_HTTPProvider):
    provider_id = "openai"

    def generate(self, request: ModelRequest, timeout_seconds: int) -> dict[str, Any]:
        instructions = request.instructions
        body: dict[str, Any] = {
            "model": self.settings.ai_model,
            "instructions": instructions,
            "input": self._input_text(request),
            "store": False,
        }
        if self.settings.ai_structured_output:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.response_schema_name,
                    "strict": True,
                    "schema": request.response_schema,
                }
            }
        else:
            body["instructions"] += "\nReturn only JSON matching this schema:\n" + json.dumps(
                request.response_schema,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        payload = self._post_json("https://api.openai.com/v1/responses", body, timeout_seconds)
        content = payload.get("output_text")
        if not isinstance(content, str):
            content = self._output_text(payload)
        return self._json_object(content, "OpenAI Responses API")

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        for item in payload.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str):
                        return text
        raise ModelProviderError("OpenAI Responses API returned no output text", "PROVIDER_RESPONSE_INVALID")


class OpenAICompatibleProvider(_HTTPProvider):
    provider_id = "openai-compatible"

    def generate(self, request: ModelRequest, timeout_seconds: int) -> dict[str, Any]:
        endpoint = self._endpoint()
        instructions = request.instructions
        if not self.settings.ai_structured_output:
            instructions += "\nReturn only JSON matching this schema:\n" + json.dumps(
                request.response_schema,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        body: dict[str, Any] = {
            "model": self.settings.ai_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": self._input_text(request)},
            ],
            "temperature": 0,
        }
        if self.settings.ai_structured_output:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema_name,
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        payload = self._post_json(endpoint, body, timeout_seconds)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelProviderError(
                "OpenAI-compatible response has no message content",
                "PROVIDER_RESPONSE_INVALID",
            ) from error
        if not isinstance(content, str):
            raise ModelProviderError(
                "OpenAI-compatible message content must be a JSON string",
                "PROVIDER_RESPONSE_INVALID",
            )
        return self._json_object(content, "OpenAI-compatible provider")

    def _endpoint(self) -> str:
        if self.settings.ai_base_url is None:
            raise ModelProviderError("OpenAI-compatible endpoint is not configured", "PROVIDER_NOT_CONFIGURED")
        endpoint = str(self.settings.ai_base_url).rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        return endpoint


class AgentHTTPProvider(_HTTPProvider):
    """Adapter for an external model gateway that implements the APS task contract."""

    provider_id = "agent-http"

    def generate(self, request: ModelRequest, timeout_seconds: int) -> dict[str, Any]:
        if self.settings.ai_base_url is None:
            raise ModelProviderError("Agent HTTP endpoint is not configured", "PROVIDER_NOT_CONFIGURED")
        payload = self._post_json(
            str(self.settings.ai_base_url),
            {
                "contract_version": 1,
                "task": request.task_id,
                "input": request.instructions.rstrip()
                + "\nInput JSON:\n"
                + json.dumps(request.input, ensure_ascii=False, separators=(",", ":")),
                "response_schema": request.response_schema,
            },
            timeout_seconds,
        )
        output = payload.get("output")
        if not isinstance(output, dict):
            raise ModelProviderError(
                "Agent HTTP response must contain an object in 'output'",
                "PROVIDER_RESPONSE_INVALID",
            )
        return output


def create_model_provider(settings: Settings) -> ModelProvider:
    configured, status = provider_status(settings)
    if not configured:
        raise ModelProviderError(
            f"model provider is not configured: {status['provider']}",
            "PROVIDER_NOT_CONFIGURED",
        )
    if settings.ai_provider == "openai":
        return OpenAIResponsesProvider(settings)
    if settings.ai_provider == "openai-compatible":
        return OpenAICompatibleProvider(settings)
    if settings.ai_provider == "agent-http":
        return AgentHTTPProvider(settings)
    raise ModelProviderError("unsupported model provider", "PROVIDER_NOT_CONFIGURED")
