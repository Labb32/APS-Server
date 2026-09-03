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


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Validated handler output before optional publication."""

    output: dict[str, Any]
    vault_commit: str | None = None
    artifacts: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: OperationName
    owner: str
    roles: frozenset[str]
    write_mode: Literal["none", "commit"]
    request_model: type[JobRequestModel]
    handler: OperationHandler
    publisher: ResultPublisher | None = None

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

    def __init__(self) -> None:
        self._specs: dict[OperationName, OperationSpec] = {}
        self._frozen = False

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
        if not isinstance(request, spec.request_model):
            raise TypeError(f"request model does not match operation: {request.operation}")
        result = spec.handler(request)
        if not isinstance(result, OperationResult):
            raise TypeError(f"operation handler returned an invalid result: {request.operation}")
        return result

    def for_role(self, role: str) -> tuple[OperationSpec, ...]:
        return tuple(spec for spec in self._specs.values() if role in spec.roles)

    @property
    def names(self) -> frozenset[OperationName]:
        return frozenset(self._specs)
