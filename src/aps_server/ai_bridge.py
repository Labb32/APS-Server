"""Fixed stdin/stdout bridge from official extensions to Core AgentExecutor."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from .agent import AgentExecutionContext, AgentExecutionError, build_agent_executor
from .config import Settings
from .extensions import ExtensionRegistry
from .vault import VaultRepository


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="APS internal extension Agent bridge")
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", args.task):
        parser.error("invalid task ID")
    prompt = sys.stdin.read()
    try:
        settings = Settings()
        vault = VaultRepository(settings.vault_path, push_after_commit=settings.vault_push_after_commit)
        extensions = ExtensionRegistry(settings.extensions_path)
        snapshot_id = os.environ.get("APS_AGENT_SNAPSHOT_ID")
        executor = build_agent_executor(settings, vault, extensions, snapshot_id)
        if args.task not in executor.tasks.task_ids() or args.task == "ideas.curate-plan":
            raise AgentExecutionError("extension Agent task is not registered", "AGENT_TASK_NOT_AVAILABLE")
        result = executor.execute(
            args.task,
            {"prompt": prompt},
            AgentExecutionContext(
                snapshot_id=snapshot_id or vault.commit(),
                capabilities=extensions.agent_task_capabilities(args.task),
            ),
        )
    except AgentExecutionError as error:
        print(error.code, file=sys.stderr)
        return 1
    except Exception as error:  # Keep prompts, provider payloads and paths out of stderr.
        print(f"Agent bridge internal failure: {type(error).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result.output.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
