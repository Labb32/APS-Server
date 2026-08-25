from __future__ import annotations

import subprocess
import threading
from pathlib import Path


class VaultError(RuntimeError):
    pass


class VaultRepository:
    def __init__(self, root: Path, timeout: int = 120) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self._sync_lock = threading.Lock()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
            raise VaultError(f"git {' '.join(args)} failed: {detail}")
        return completed.stdout.strip()

    def commit(self) -> str:
        return self._git("rev-parse", "HEAD")

    def sync(self) -> str:
        with self._sync_lock:
            if not (self.root / ".git").exists():
                raise VaultError(f"Vault is not a Git repository: {self.root}")
            if self._git("status", "--porcelain"):
                raise VaultError("Vault worktree is dirty; automatic sync refused")
            self._git("fetch", "--prune", "origin")
            upstream = self._git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
            head = self.commit()
            upstream_commit = self._git("rev-parse", upstream)
            ancestor = subprocess.run(
                [
                    "git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root),
                    "merge-base", "--is-ancestor", head, upstream_commit,
                ],
                timeout=self.timeout,
                check=False,
            )
            if ancestor.returncode != 0:
                raise VaultError("Vault cannot be fast-forwarded to its upstream")
            self._git("merge", "--ff-only", upstream)
            return self.commit()
