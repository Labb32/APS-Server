"""Minimal Git boundary for one APS Vault.

The repository deliberately exposes neither arbitrary commands nor merge and
reset helpers.  Synchronization accepts clean fast-forward updates only.
"""

from __future__ import annotations

import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class VaultError(RuntimeError):
    code = "VAULT_SYNC_FAILED"


class VaultDirtyError(VaultError):
    code = "VAULT_DIRTY"


class VaultNotFastForwardError(VaultError):
    code = "VAULT_NOT_FAST_FORWARD"


class VaultNotRepositoryError(VaultError):
    code = "VAULT_NOT_REPOSITORY"


class VaultRepository:
    def __init__(self, root: Path, timeout: int = 120) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self._sync_lock = threading.RLock()

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

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self._sync_lock:
            yield

    def require_clean(self) -> None:
        if self._git("status", "--porcelain"):
            raise VaultDirtyError("Vault worktree is dirty; write refused")

    def is_ignored(self, path: Path) -> bool:
        relative = path.resolve().relative_to(self.root).as_posix()
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root), "check-ignore", "--quiet", "--", relative],
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            raise VaultError("git check-ignore failed")
        return completed.returncode == 0

    def commit_paths(self, paths: list[Path], message: str) -> str:
        if not paths:
            return self.commit()
        # ``relative_to`` is also a containment check: callers cannot stage a
        # path outside the configured Vault.
        relative = [path.resolve().relative_to(self.root).as_posix() for path in paths]
        self._git("add", "--", *relative)
        staged = self._git("diff", "--cached", "--name-only", "--", *relative)
        if not staged:
            return self.commit()
        self._git(
            "-c", "user.name=APS Server", "-c", "user.email=aps-server@localhost",
            "commit", "-m", message, "--", *relative,
        )
        return self.commit()

    def sync(self) -> str:
        with self._sync_lock:
            if not (self.root / ".git").exists():
                raise VaultNotRepositoryError(f"Vault is not a Git repository: {self.root}")
            self.require_clean()
            self._git("fetch", "--prune", "origin")
            upstream = self._git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
            head = self.commit()
            upstream_commit = self._git("rev-parse", upstream)
            # Never repair divergence automatically.  An operator must resolve
            # it in the Vault clone before APS Server resumes writes.
            ancestor = subprocess.run(
                [
                    "git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root),
                    "merge-base", "--is-ancestor", head, upstream_commit,
                ],
                timeout=self.timeout,
                check=False,
            )
            if ancestor.returncode != 0:
                raise VaultNotFastForwardError("Vault cannot be fast-forwarded to its upstream")
            self._git("merge", "--ff-only", upstream)
            return self.commit()
