"""Restricted subprocess host for installed official extensions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .config import Settings
from .extensions import ExtensionRegistry
from .models import CreateJobRequest
from .vault import VaultRepository


class ExtensionHostError(RuntimeError):
    def __init__(self, message: str, code: str = "EXTENSION_EXECUTION_FAILED") -> None:
        super().__init__(message)
        self.code = code


class ExtensionHost:
    """Runs only a manifest-owned entrypoint with a fixed JSON contract.

    Request fields never become executable names, paths, arguments, or
    environment variables. The operation must already belong to an installed
    official extension in the immutable process registry.
    """

    def __init__(
        self,
        settings: Settings,
        extensions: ExtensionRegistry,
        vault: VaultRepository,
    ) -> None:
        self.settings = settings
        self.extensions = extensions
        self.vault = vault

    def execute(self, request: CreateJobRequest) -> dict[str, Any]:
        try:
            owner = self.extensions.operation_owners[request.operation]
            manifest = self.extensions.manifests[owner]
        except KeyError as error:
            raise ExtensionHostError("operation has no active extension owner", "EXTENSION_NOT_READY") from error

        entrypoint = (self.extensions.installed_root / owner / manifest.entrypoint).resolve()
        work_root = (self.settings.data_path / "work").resolve()
        if work_root == self.vault.root or work_root.is_relative_to(self.vault.root):
            raise ExtensionHostError(
                "extension work directory must be outside the Vault",
                "EXTENSION_SNAPSHOT_INVALID",
            )
        try:
            work_root.mkdir(parents=True, exist_ok=True)
            with self.vault.locked():
                self.vault.require_clean()
                snapshot_id = self.vault.commit()
                with tempfile.TemporaryDirectory(prefix="extension-", dir=work_root) as temporary:
                    snapshot_root = Path(temporary) / "vault"
                    shutil.copytree(
                        self.vault.root,
                        snapshot_root,
                        ignore=self._snapshot_ignores,
                    )
                    return self._run(entrypoint, request, snapshot_root, snapshot_id)
        except ExtensionHostError:
            raise
        except OSError as error:
            raise ExtensionHostError("extension snapshot could not be prepared", "EXTENSION_SNAPSHOT_FAILED") from error

    @staticmethod
    def _snapshot_ignores(directory: str, names: list[str]) -> set[str]:
        root = Path(directory)
        return {
            name
            for name in names
            if name in {".git", "00_Inbox"} or (root / name).is_symlink()
        }

    def _run(
        self,
        entrypoint: Path,
        request: CreateJobRequest,
        snapshot_root: Path,
        snapshot_id: str,
    ) -> dict[str, Any]:
        # Do not copy API tokens or Git configuration into extension
        # environments. Provider credentials remain necessary for the fixed
        # Agent bridge and are redacted from extension failures below.
        environment = {
            key: os.environ[key]
            for key in ("PATH", "LANG", "LC_ALL", "TZ", "PYTHONPATH")
            if key in os.environ
        }
        environment.update(
            {
                "APS_AI_PROVIDER": self.settings.ai_provider,
                "APS_AI_MODEL": self.settings.ai_model,
                "APS_AI_TIMEOUT_SECONDS": str(self.settings.ai_timeout_seconds),
                "APS_AI_PARALLEL_REQUESTS": str(self.settings.ai_parallel_requests),
                "APS_AI_MAX_INPUT_CHARS": str(self.settings.ai_max_input_chars),
                "APS_AI_STRUCTURED_OUTPUT": str(self.settings.ai_structured_output).lower(),
                # The extension may invoke the fixed Core Agent bridge from a
                # Vault working directory. Pass resolved internal roots so it
                # never depends on cwd or a request-supplied path.
                "APS_VAULT_PATH": str(snapshot_root),
                "APS_EXTENSIONS_PATH": str(self.extensions.installed_root.resolve()),
                "APS_AGENT_SNAPSHOT_ID": snapshot_id,
                "HOME": str(snapshot_root),
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        if self.settings.ai_base_url:
            environment["APS_AI_BASE_URL"] = str(self.settings.ai_base_url)
        else:
            environment.pop("APS_AI_BASE_URL", None)
        if self.settings.ai_api_key:
            environment["APS_AI_API_KEY"] = self.settings.ai_api_key.get_secret_value()
        else:
            environment.pop("APS_AI_API_KEY", None)

        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(entrypoint),
                    "--aps-operation",
                    request.operation.value,
                    "--vault",
                    str(snapshot_root),
                ],
                cwd=snapshot_root,
                input=request.model_dump_json(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.job_timeout_seconds,
                env=environment,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExtensionHostError("extension process could not complete") from error
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "no output").strip()
            if self.settings.ai_api_key:
                detail = detail.replace(self.settings.ai_api_key.get_secret_value(), "***")
            raise ExtensionHostError(f"extension failed ({completed.returncode}): {detail[-4000:]}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ExtensionHostError("extension returned invalid JSON", "EXTENSION_OUTPUT_INVALID") from error
        if not isinstance(payload, dict):
            raise ExtensionHostError("extension result must be a JSON object", "EXTENSION_OUTPUT_INVALID")
        return payload
