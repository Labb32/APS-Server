"""Immutable registry and result contract for predefined APS operations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel

from ..models import CreateJobRequest, JobRequestModel, OperationName


OperationHandler = Callable[[CreateJobRequest], "OperationResult"]
ResultPublisher = Callable[[dict[str, Any], str], list[Any]]
_ROLE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class OperationRegistryError(RuntimeError):
    code = "OPERATION_NOT_AVAILABLE"


class OperationUnavailableError(OperationRegistryError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class OperationAvailability:
    enabled: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Validated handler output before optional publication."""

    output: dict[str, Any]
    vault_commit: str | None = None
    artifacts: tuple[Any, ...] = field(default_factory=tuple)
    result_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: OperationName
    owner: str
    roles: frozenset[str]
    write_mode: Literal["none", "commit"]
    request_model: type[JobRequestModel]
    handler: OperationHandler
    publisher: ResultPublisher | None = None
    requires_ai: bool = False

    def __post_init__(self) -> None:
        if not _ROLE.fullmatch(self.owner):
            raise ValueError("invalid operation owner")
        if not self.roles or any(not _ROLE.fullmatch(role) for role in self.roles):
            raise ValueError("operation roles must be non-empty identifiers")
        if self.write_mode not in {"none", "commit"}:
            raise ValueError("invalid operation write mode")
        if not isinstance(self.request_model, type) or not issubclass(self.request_model, BaseModel):
            raise TypeError("operation request_model must be a Pydantic model")


class OperationRegistry:
    """Operation policy surface assembled once during application startup."""

    def __init__(self, ai_enabled: bool = False, ai_configured: bool = False) -> None:
        self._specs: dict[OperationName, OperationSpec] = {}
        self._frozen = False
        self._ai_enabled = ai_enabled
        self._ai_configured = ai_configured

    def register(self, spec: OperationSpec) -> None:
        if self._frozen:
            raise RuntimeError("operation registry is frozen")
        if spec.name in self._specs:
            raise ValueError(f"duplicate operation: {spec.name}")
        self._specs[spec.name] = spec

    def freeze(self) -> None:
        self._frozen = True

    def get(self, name: OperationName) -> OperationSpec:
        try:
            return self._specs[name]
        except KeyError as error:
            raise OperationRegistryError(f"operation is not registered: {name.value}") from error

    def execute(self, request: CreateJobRequest) -> OperationResult:
        spec = self.get(request.operation)
        self.require_available(spec)
        if not isinstance(request, spec.request_model):
            raise TypeError(f"request model does not match operation: {request.operation}")
        result = spec.handler(request)
        if not isinstance(result, OperationResult):
            raise TypeError(f"operation handler returned an invalid result: {request.operation}")
        return result

    def for_role(self, role: str) -> tuple[OperationSpec, ...]:
        return tuple(spec for spec in self._specs.values() if role in spec.roles)

    def availability(self, spec: OperationSpec) -> OperationAvailability:
        if not spec.requires_ai:
            return OperationAvailability(True)
        if not self._ai_enabled:
            return OperationAvailability(False, "AI_DISABLED")
        if not self._ai_configured:
            return OperationAvailability(False, "PROVIDER_NOT_CONFIGURED")
        return OperationAvailability(True)

    def require_available(self, spec: OperationSpec) -> None:
        availability = self.availability(spec)
        if not availability.enabled:
            raise OperationUnavailableError(availability.reason or "OPERATION_NOT_AVAILABLE", "AI operation is unavailable")

    @property
    def names(self) -> frozenset[OperationName]:
        return frozenset(self._specs)
