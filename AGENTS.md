# APS Server Agent Guide

- This repository owns the container, API, queue, worker and deployment code. APS Vault owns project and service documents.
- Never add personal schedules or unrelated life-management data.
- Keep Vault synchronization fast-forward only. Do not add automatic merge, reset, force checkout or force push behavior.
- Do not expose arbitrary shell commands, executable paths or Codex arguments through the API.
- Treat Vault writes as out of scope until a proposal-branch and explicit approval flow exists.
- Keep `agent.query` limited to normalized paths copied into an isolated context directory.
- Preserve the documented API contract and add tests for every operation or permission change.
- Keep the container on one web process while the queue is in-process.
