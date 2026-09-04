"""Minimal Git boundary for one APS Vault.

The repository deliberately exposes neither arbitrary commands nor merge and
reset helpers.  Synchronization accepts clean fast-forward updates only.
"""

from __future__ import annotations

import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


_URL_CREDENTIAL = re.compile(r"(?P<scheme>https?://)[^/@\s]+@", re.IGNORECASE)


def _redact_git_output(value: str) -> str:
    return _URL_CREDENTIAL.sub(r"\g<scheme>***@", value)


class VaultError(RuntimeError):
    code = "VAULT_SYNC_FAILED"


class VaultDirtyError(VaultError):
    code = "VAULT_DIRTY"


class VaultNotFastForwardError(VaultError):
    code = "VAULT_NOT_FAST_FORWARD"


class VaultNotRepositoryError(VaultError):
    code = "VAULT_NOT_REPOSITORY"


class VaultPushError(VaultError):
    code = "VAULT_PUSH_FAILED"


@dataclass(frozen=True)
class TrackingBranch:
    remote: str
    branch: str

    @property
    def ref(self) -> str:
        return f"refs/remotes/{self.remote}/{self.branch}"


class VaultRepository:
    def __init__(self, root: Path, timeout: int = 120, push_after_commit: bool = False) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self.push_after_commit = push_after_commit
        self._sync_lock = threading.RLock()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            [
                "git",
                "-c", f"safe.directory={self.root.as_posix()}",
                "-c", "core.hooksPath=/dev/null",
                "-c", "core.fsmonitor=false",
                "-c", "commit.gpgSign=false",
                "-C", str(self.root),
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode:
            detail = _redact_git_output(completed.stderr.strip() or completed.stdout.strip() or "no output")
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
        commit = self.commit()
        if self.push_after_commit:
            try:
                self.push()
            except VaultError as error:
                # The commit is durable and must not be disguised as an
                # uncommitted worktree rollback when the network push fails.
                raise VaultPushError(f"Vault commit {commit} was created but could not be pushed: {error}") from error
        return commit

    def _is_ancestor(self, ancestor: str, descendant: str) -> bool:
        completed = subprocess.run(
            [
                "git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root),
                "merge-base", "--is-ancestor", ancestor, descendant,
            ],
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            raise VaultError("git merge-base failed")
        return completed.returncode == 0

    def _tracking_branch(self) -> TrackingBranch:
        local_branch = self._git("symbolic-ref", "--quiet", "--short", "HEAD")
        completed = subprocess.run(
            [
                "git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root),
                "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode == 0:
            upstream = completed.stdout.strip()
            configured_remote = subprocess.run(
                [
                    "git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root),
                    "config", "--get", f"branch.{local_branch}.remote",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
            remote = configured_remote.stdout.strip() if configured_remote.returncode == 0 else ""
            prefix = f"{remote}/"
            if not remote or not upstream.startswith(prefix):
                raise VaultError("Vault upstream does not match its tracking remote")
            branch = upstream.removeprefix(prefix)
        else:
            remote = "origin"
            branch = local_branch
        if not remote or not branch or branch == "HEAD":
            raise VaultError("Vault branch must track a concrete remote branch")
        if remote not in self._git("remote").splitlines():
            raise VaultError("Vault tracking remote does not exist")
        self._git("check-ref-format", "--branch", branch)
        return TrackingBranch(remote=remote, branch=branch)

    def push(self) -> str:
        """Push HEAD to its tracking branch without rewriting remote history."""
        with self._sync_lock:
            self.require_clean()
            tracking = self._tracking_branch()
            self._git("fetch", "--prune", tracking.remote)
            head = self.commit()
            upstream_commit = self._git("rev-parse", tracking.ref)
            if not self._is_ancestor(upstream_commit, head):
                raise VaultNotFastForwardError("Vault cannot be pushed without a fast-forward")
            self._git("push", "--porcelain", tracking.remote, f"HEAD:refs/heads/{tracking.branch}")
            return head

    def sync(self) -> str:
        with self._sync_lock:
            if not (self.root / ".git").exists():
                raise VaultNotRepositoryError(f"Vault is not a Git repository: {self.root}")
            self.require_clean()
            tracking = self._tracking_branch()
            self._git("fetch", "--prune", tracking.remote)
            head = self.commit()
            upstream_commit = self._git("rev-parse", tracking.ref)
            if self._is_ancestor(head, upstream_commit):
                self._git("merge", "--ff-only", tracking.ref)
            elif not self._is_ancestor(upstream_commit, head):
                raise VaultNotFastForwardError("Vault cannot be fast-forwarded to its upstream")
            return self.commit()
