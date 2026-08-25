from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def request(method: str, path: str, payload=None):
    base_url = os.environ.get("APS_API_URL", "http://127.0.0.1:8080").rstrip("/")
    token = os.environ.get("APS_API_TOKEN", "")
    if not token:
        raise RuntimeError("APS_API_TOKEN is required")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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
    daily.add_argument("--format", choices=["html", "json"], default="html")
    daily.add_argument("--wait", action="store_true")
    project = subparsers.add_parser("briefing-project")
    project.add_argument("project_id")
    project.add_argument("--format", choices=["html", "json"], default="html")
    project.add_argument("--wait", action="store_true")
    audit = subparsers.add_parser("vault-audit")
    audit.add_argument("--wait", action="store_true")
    get = subparsers.add_parser("jobs-get")
    get.add_argument("job_id")
    args = parser.parse_args()

    if args.command == "jobs-get":
        result = request("GET", f"/v1/jobs/{args.job_id}")
    else:
        operations = {
            "briefing-daily": ("briefing.daily", {"format": args.format}, {}),
            "briefing-project": ("briefing.project", {"format": args.format}, {"project_ids": [args.project_id]}),
            "vault-audit": ("vault.audit", {}, {}),
        }
        operation, inputs, context = operations[args.command]
        result = request("POST", "/v1/jobs", {"operation": operation, "input": inputs, "context": context})
        if args.wait:
            result = wait_for(result["job_id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
