# APS Server Agent Guide

- This repository owns the container, API, queue, worker and deployment code. APS Vault owns project and service documents.
- Never add personal schedules or unrelated life-management data.
- Keep Vault synchronization fast-forward only. Do not add automatic merge, reset, force checkout or force push behavior.
- Do not expose arbitrary shell commands, executable paths or Codex arguments through the API.
- Allow Idea intake writes only in the fixed Git-ignored Vault `00_Inbox`; never accept a requester-supplied path. Tracked Idea writes are limited to validated `01_Ideas`/`01_Idea_Sets` targets through the documented Scheduler commit flow. Other tracked Vault writes remain out of scope until a proposal-branch and explicit approval flow exists.
- Do not reintroduce free-form agent queries or requester-supplied Vault paths; content endpoints serve predefined materialized results.
- Preserve the documented API contract. Do not add new test files or test cases unless the user explicitly requests them; verify changes by directly running the relevant API, permission and service flows instead.
- Keep the container on one web process while the queue is in-process.
