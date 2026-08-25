from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import Settings
from .models import Artifact, CreateJobRequest, OperationName
from .vault import VaultError, VaultRepository


POLICIES: dict[OperationName, dict[str, Any]] = {
    OperationName.BRIEFING_DAILY: {"roles": {"scheduler", "operator", "viewer"}, "write_mode": "none"},
    OperationName.BRIEFING_PROJECT: {"roles": {"operator", "viewer"}, "write_mode": "none"},
    OperationName.VAULT_AUDIT: {"roles": {"scheduler", "operator"}, "write_mode": "none"},
    OperationName.SERVICE_MAINTENANCE_DUE: {"roles": {"scheduler", "operator", "viewer"}, "write_mode": "none"},
}


class OperationError(RuntimeError):
    pass


class OperationExecutor:
    def __init__(self, settings: Settings, vault: VaultRepository) -> None:
        self.settings = settings
        self.vault = vault

    def execute(self, job_id: str, request: CreateJobRequest) -> tuple[dict[str, Any], list[Artifact], dict[str, str]]:
        if request.operation == OperationName.VAULT_AUDIT:
            return self._vault_audit(), [], {}
        if request.operation == OperationName.SERVICE_MAINTENANCE_DUE:
            return self._service_due(request), [], {}
        if request.operation in {OperationName.BRIEFING_DAILY, OperationName.BRIEFING_PROJECT}:
            return self._briefing(job_id, request)
        raise OperationError(f"unsupported operation: {request.operation}")

    def _run(self, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.job_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OperationError(str(error)) from error
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "no output").strip()
            raise OperationError(f"command failed ({completed.returncode}): {detail[-4000:]}")
        return completed

    def _briefing(self, job_id: str, request: CreateJobRequest):
        script = self.vault.root / "scripts" / "daily_briefing.py"
        if not script.is_file():
            raise OperationError("Vault briefing script is missing")
        output_format = str(request.input.get("format", "html"))
        if output_format not in {"html", "json"}:
            raise OperationError("format must be html or json")
        project_ids = request.context.project_ids
        if request.operation == OperationName.BRIEFING_PROJECT and len(project_ids) != 1:
            raise OperationError("briefing.project requires exactly one project_id")

        command = [sys.executable, str(script), "--no-pull"]
        if project_ids:
            command.extend(["--project", project_ids[0]])
        if output_format == "json":
            command.append("--json")
            completed = self._run(command, self.vault.root)
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise OperationError("briefing returned invalid JSON") from error
            return payload, [], {}

        artifact_dir = self.settings.data_path / "artifacts" / job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        output = artifact_dir / "briefing.html"
        command.extend(["--html", str(output), "--no-open"])
        self._run(command, self.vault.root)
        if not output.is_file() or output.stat().st_size < 1024:
            raise OperationError("generated briefing HTML failed validation")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        artifact = Artifact(
            artifact_id="briefing-html",
            media_type="text/html",
            download_url=f"/v1/jobs/{job_id}/artifacts/briefing-html",
            sha256=digest,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        return {"format": "html", "bytes": output.stat().st_size}, [artifact], {artifact.artifact_id: str(output)}

    def _service_due(self, request: CreateJobRequest) -> dict[str, Any]:
        script = self.vault.root / "scripts" / "daily_briefing.py"
        command = [sys.executable, str(script), "--dry-run", "--json", "--no-pull"]
        if request.input.get("date"):
            command.extend(["--today", str(request.input["date"])])
        completed = self._run(command, self.vault.root)
        payload = json.loads(completed.stdout)
        return {
            "date": payload.get("date"),
            "maintenance": payload.get("service_maintenance_markdown", []),
        }

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
