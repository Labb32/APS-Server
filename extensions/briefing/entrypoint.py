#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parent
LEGACY_PATH = ROOT / "legacy" / "daily_briefing.py"
RESPONSE_SCHEMA_PATH = ROOT / "schemas" / "briefing_response.schema.json"


def load_legacy() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aps_official_briefing_legacy", LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"legacy briefing module cannot be loaded: {LEGACY_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.RESPONSE_SCHEMA_PATH = RESPONSE_SCHEMA_PATH
    return module


def stable_id(prefix: str, value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        slug = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{slug}"[:80].rstrip("-")


def project_records(legacy: ModuleType, notes: list[Any], results: list[Any]) -> list[dict[str, Any]]:
    note_by_id = {note.metadata.get("briefing_id", ""): note for note in notes}
    records: list[dict[str, Any]] = []
    for result in results:
        note = note_by_id.get(result.briefing_id)
        metadata = note.metadata if note else {}
        issues = []
        if result.status == "abnormal":
            message = " ".join(result.notes) or "프로젝트 브리핑 생성에 실패했습니다."
            issues.append(
                {
                    "code": "BRIEFING_ABNORMAL",
                    # Provider stderr can be unexpectedly large. Keep the
                    # public canonical error within its documented limit.
                    "message": message[:1000],
                    "subject_id": result.briefing_id,
                }
            )
        records.append(
            {
                "project_id": result.briefing_id,
                "name": result.name,
                "status": metadata.get("status", result.status),
                "tier": metadata.get("tier") or None,
                "summary": metadata.get("summary") or "APS ProjectContext를 기준으로 생성한 일일 브리핑입니다.",
                "tasks": [
                    {
                        "task_id": f"brief-{index}",
                        "title": task,
                        "completion": task,
                        "status": "pending",
                    }
                    for index, task in enumerate(result.today_tasks, start=1)
                ],
                "decisions": [],
                "issues": issues,
            }
        )
    return records


def service_records(legacy: ModuleType, notes: list[Any], today: date) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for note in notes:
        if note.metadata.get("service_status") not in legacy.ACTIVE_SERVICE_STATES:
            continue
        issues: list[dict[str, Any]] = []
        interval: int | None = None
        last: date | None = None
        due: date | None = None
        due_status = "unknown"
        days_overdue = 0
        try:
            raw_interval = note.metadata.get("maintenance_interval_days", "")
            parsed_interval = int(raw_interval)
            if parsed_interval < 0:
                raise ValueError("maintenance_interval_days must be zero or greater")
            if parsed_interval > 0:
                interval = parsed_interval
                last = legacy.parse_iso_date(note.metadata.get("last_maintenance", ""), "last_maintenance", note.path)
                due = last + timedelta(days=interval)
                if today < due:
                    due_status = "upcoming"
                elif today == due:
                    due_status = "due"
                else:
                    due_status = "overdue"
                    days_overdue = (today - due).days
        except (TypeError, ValueError) as error:
            issues.append(
                {
                    "code": "MAINTENANCE_METADATA_INVALID",
                    "message": str(error),
                    "subject_id": note.path.name,
                }
            )
        records.append(
            {
                "service_id": stable_id("service", note.path.stem),
                "name": note.title,
                "service_status": note.metadata.get("service_status", "unknown"),
                "maintenance_cycle": note.metadata.get("maintenance_cycle") or None,
                "maintenance_interval_days": interval,
                "last_maintenance": last.isoformat() if last else None,
                "next_maintenance_due": due.isoformat() if due else None,
                "due_status": due_status,
                "days_overdue": days_overdue,
                "maintenance_summary": note.metadata.get("maintenance_summary") or None,
                "issues": issues,
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APS official briefing extension")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--today")
    parser.add_argument("--project")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", required=True)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    vault = args.vault.resolve()
    if not vault.is_dir():
        raise RuntimeError(f"APS Vault directory does not exist: {vault}")
    today = date.fromisoformat(args.today) if args.today else date.today()
    legacy = load_legacy()

    projects = legacy.load_notes(vault / "02_Projects")
    services = legacy.load_notes(vault / "03_Services")
    config = {
        "runner": {
            # Provider selection remains in APS Core; the extension invokes a
            # fixed bridge and cannot choose a model, endpoint or executable.
            "command": [sys.executable, "-m", "aps_server.ai_bridge", "--schema", "briefing"],
            "timeout_seconds": int(os.environ.get("APS_AI_TIMEOUT_SECONDS", "600")),
            "parallel_projects": int(os.environ.get("APS_AI_PARALLEL_REQUESTS", "3")),
        }
    }
    results = legacy.run_project_briefings(
        projects,
        config,
        vault,
        today,
        args.dry_run,
        args.project,
    )
    project_data = project_records(legacy, projects, results)
    service_data = service_records(legacy, services, today)
    partial_failure = any(project["issues"] for project in project_data) or any(service["issues"] for service in service_data)
    payload = {
        "partial_failure": partial_failure,
        "data": {
            "as_of_date": today.isoformat(),
            "summary": {
                "active_projects": len(project_data),
                "tasks": sum(len(project["tasks"]) for project in project_data),
                "decisions": sum(len(project["decisions"]) for project in project_data),
                "services_due": sum(service["due_status"] in {"due", "overdue"} for service in service_data),
            },
            "projects": project_data,
            "service_maintenance": service_data,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
