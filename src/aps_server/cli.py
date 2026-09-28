from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from .config import Settings
from .extensions import OfficialExtensionInstaller


def request(method: str, path: str, payload=None, extra_headers: dict[str, str] | None = None):
    base_url = os.environ.get("APS_API_URL", "http://127.0.0.1:8080").rstrip("/")
    token = os.environ.get("APS_API_TOKEN", "")
    if not token:
        raise RuntimeError("APS_API_TOKEN is required")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    call = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode("utf-8", errors="replace")) from error


def wait_for(job_id: str):
    while True:
        job = request("GET", f"/v1/jobs/{job_id}")
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(prog="aps")
    subparsers = parser.add_subparsers(dest="command", required=True)
    daily = subparsers.add_parser("briefing-daily")
    daily.add_argument("--wait", action="store_true")
    project = subparsers.add_parser("briefing-project")
    project.add_argument("project_id")
    project.add_argument("--wait", action="store_true")
    audit = subparsers.add_parser("vault-audit")
    audit.add_argument("--wait", action="store_true")
    ideas = subparsers.add_parser("ideas-refresh")
    ideas.add_argument("--wait", action="store_true")
    curate = subparsers.add_parser("ideas-curate")
    curate.add_argument("--wait", action="store_true")
    get = subparsers.add_parser("jobs-get")
    get.add_argument("job_id")
    schedule_run = subparsers.add_parser("schedule-run")
    schedule_run.add_argument("schedule_id")
    schedule_run.add_argument("--scheduled-for")
    extensions = subparsers.add_parser("extensions")
    extension_commands = extensions.add_subparsers(dest="extension_command", required=True)
    extension_commands.add_parser("list")
    install = extension_commands.add_parser("install")
    install.add_argument("extension_id")
    args = parser.parse_args()

    if args.command == "extensions":
        settings = Settings()
        installer = OfficialExtensionInstaller(settings.official_extensions_path, settings.extensions_path)
        if args.extension_command == "list":
            result = installer.list().model_dump(mode="json")
        else:
            try:
                result = installer.install(args.extension_id).model_dump(mode="json")
            except KeyError as error:
                raise RuntimeError(f"unknown official extension: {args.extension_id}") from error
    elif args.command == "jobs-get":
        result = request("GET", f"/v1/jobs/{args.job_id}")
    elif args.command == "schedule-run":
        status = request("GET", "/v1/scheduler")
        if not status["enabled"] or status["backend"] != "external-cli":
            raise RuntimeError("external Scheduler backend is not active")
        schedule = next((item for item in status["schedules"] if item["schedule_id"] == args.schedule_id), None)
        if schedule is None:
            raise RuntimeError(f"unknown schedule: {args.schedule_id}")
        if not schedule["enabled"]:
            raise RuntimeError(f"schedule is disabled: {args.schedule_id}")
        if args.scheduled_for:
            try:
                scheduled_for = datetime.fromisoformat(args.scheduled_for.replace("Z", "+00:00"))
                if scheduled_for.utcoffset() is None:
                    raise ValueError
                scheduled_for = scheduled_for.astimezone(UTC)
            except ValueError as error:
                raise RuntimeError("--scheduled-for must be an ISO 8601 timestamp") from error
        else:
            scheduled_for = datetime.now(UTC)
        scheduled_for = scheduled_for.replace(second=0, microsecond=0)
        key_source = f"schedule:{args.schedule_id}:{scheduled_for.isoformat()}"
        key = "schedule-" + hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        result = request(
            "POST",
            "/v1/jobs",
            schedule["request"],
            {"Idempotency-Key": key},
        )
    else:
        if args.command == "briefing-project":
            operation, inputs, context = "briefing.project", {}, {"project_ids": [args.project_id]}
        else:
            operation, inputs, context = {
                "briefing-daily": ("briefing.daily", {}, {}),
                "vault-audit": ("vault.audit", {}, {}),
                "ideas-refresh": ("ideas.index.refresh", {}, {}),
                "ideas-curate": ("ideas.curate", {}, {}),
            }[args.command]
        result = request("POST", "/v1/jobs", {"operation": operation, "input": inputs, "context": context})
        if args.wait:
            result = wait_for(result["job_id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
