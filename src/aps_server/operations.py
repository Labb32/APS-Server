"""Fixed operation allowlist and Vault-backed operation executor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .brief_extension import BriefExtension, BriefExtensionError
from .config import Settings
from .idea_catalog import IdeaCatalogError, load_idea_catalog
from .idea_service import IdeaService, IdeaServiceError
from .models import CreateJobRequest, OperationName
from .vault import VaultRepository


POLICIES: dict[OperationName, dict[str, Any]] = {
    OperationName.BRIEFING_DAILY: {"roles": {"scheduler", "operator", "viewer"}, "write_mode": "none"},
    OperationName.BRIEFING_PROJECT: {"roles": {"operator", "viewer"}, "write_mode": "none"},
    OperationName.VAULT_AUDIT: {"roles": {"scheduler", "operator"}, "write_mode": "none"},
    OperationName.SERVICE_MAINTENANCE_DUE: {"roles": {"scheduler", "operator", "viewer"}, "write_mode": "none"},
    OperationName.IDEAS_INDEX_REFRESH: {"roles": {"scheduler", "operator"}, "write_mode": "none"},
    OperationName.IDEAS_CURATE: {"roles": {"scheduler", "operator"}, "write_mode": "commit"},
}


class OperationError(RuntimeError):
    def __init__(self, message: str, code: str = "OPERATION_FAILED") -> None:
        super().__init__(message)
        self.code = code


class OperationExecutor:
    def __init__(self, settings: Settings, vault: VaultRepository) -> None:
        self.settings = settings
        self.vault = vault
        self.brief = BriefExtension(settings.extensions_path)

    def execute(self, request: CreateJobRequest) -> dict[str, Any]:
        if request.operation == OperationName.VAULT_AUDIT:
            return self._vault_audit()
        if request.operation == OperationName.SERVICE_MAINTENANCE_DUE:
            return self._service_due(request)
        if request.operation in {OperationName.BRIEFING_DAILY, OperationName.BRIEFING_PROJECT}:
            return self._briefing(request)
        if request.operation == OperationName.IDEAS_INDEX_REFRESH:
            return self._ideas_index(request)
        if request.operation == OperationName.IDEAS_CURATE:
            return self._ideas_curate()
        raise OperationError(f"unsupported operation: {request.operation}")

    def _run(self, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        # Pass only the Core-selected AI configuration to the official child
        # process. No request field can alter these values.
        environment = os.environ.copy()
        environment.update(
            {
                "APS_AI_PROVIDER": self.settings.ai_provider,
                "APS_AI_MODEL": self.settings.ai_model,
                "APS_AI_TIMEOUT_SECONDS": str(self.settings.ai_timeout_seconds),
                "APS_AI_PARALLEL_REQUESTS": str(self.settings.ai_parallel_requests),
                "APS_AI_MAX_INPUT_CHARS": str(self.settings.ai_max_input_chars),
                "APS_AI_STRUCTURED_OUTPUT": str(self.settings.ai_structured_output).lower(),
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
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.job_timeout_seconds,
                env=environment,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OperationError(str(error), "PROVIDER_EXECUTION_FAILED") from error
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "no output").strip()
            raise OperationError(f"command failed ({completed.returncode}): {detail[-4000:]}", "PROVIDER_EXECUTION_FAILED")
        return completed

    @staticmethod
    def _json_output(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise OperationError("extension returned invalid JSON", "PROVIDER_OUTPUT_INVALID") from error
        if not isinstance(payload, dict):
            raise OperationError("extension JSON result must be an object", "PROVIDER_OUTPUT_INVALID")
        return payload

    def _extension_command(self) -> list[str]:
        try:
            self.brief.require()
        except BriefExtensionError as error:
            raise OperationError(str(error), "EXTENSION_NOT_READY") from error
        return [
            sys.executable,
            str(self.brief.entrypoint),
            "--vault",
            str(self.vault.root),
            "--json",
        ]

    def _briefing(self, request: CreateJobRequest) -> dict[str, Any]:
        command = self._extension_command()
        if request.operation == OperationName.BRIEFING_PROJECT:
            command.extend(["--project", request.context.project_ids[0]])
        return self._json_output(self._run(command, self.vault.root))

    def _service_due(self, request: CreateJobRequest) -> dict[str, Any]:
        command = self._extension_command()
        command.append("--dry-run")
        if request.input.date:
            command.extend(["--today", request.input.date.isoformat()])
        return self._json_output(self._run(command, self.vault.root))

    def _vault_audit(self) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        projects = self.vault.root / "02_Projects"
        active_count = 0
        for note in sorted(projects.glob("*.md")):
            content = note.read_text(encoding="utf-8-sig")
            frontmatter = content.split("---", 2)[1] if content.startswith("---") and content.count("---") >= 2 else ""
            metadata = {}
            for line in frontmatter.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.split(" #", 1)[0].strip()
            if metadata.get("status") != "In_Progress":
                continue
            active_count += 1
            briefing_id = metadata.get("briefing_id", "")
            if not briefing_id:
                issues.append({"path": note.name, "code": "MISSING_BRIEFING_ID"})
                continue
            prompt = self.vault.root / "05_ProjectContexts" / briefing_id / ".brief" / "brief.md"
            if not prompt.is_file():
                issues.append({"path": note.name, "code": "MISSING_BRIEF_PROMPT"})
        return {"active_projects": active_count, "issues": issues, "healthy": not issues}

    def _ideas_index(self, request: CreateJobRequest) -> dict[str, Any]:
        try:
            return load_idea_catalog(self.vault.root)
        except (OSError, IdeaCatalogError) as error:
            raise OperationError(str(error), "IDEA_CATALOG_INVALID") from error

    def _ideas_curate(self) -> dict[str, Any]:
        try:
            return IdeaService(self.vault, sync_before_write=False).curate()
        except (OSError, IdeaCatalogError, IdeaServiceError) as error:
            code = error.code if isinstance(error, IdeaServiceError) else "IDEA_CURATION_FAILED"
            raise OperationError(str(error), code) from error
