from __future__ import annotations

import shutil
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

    def resolve_scoped_path(self, relative: str) -> Path:
        source = (self.root / relative).resolve()
        try:
            source.relative_to(self.root)
        except ValueError as error:
            raise VaultError(f"path escapes Vault: {relative}") from error
        if not source.exists():
            raise VaultError(f"Vault path does not exist: {relative}")
        return source

    def project_paths(self, briefing_id: str) -> list[str]:
        matches: list[str] = []
        projects = self.root / "02_Projects"
        for note in sorted(projects.glob("*.md")):
            text = note.read_text(encoding="utf-8-sig")
            if any(line.strip() == f"briefing_id: {briefing_id}" for line in text.splitlines()[:20]):
                matches.append(note.relative_to(self.root).as_posix())
                break
        context = self.root / "05_ProjectContexts" / briefing_id
        if context.is_dir():
            matches.append(context.relative_to(self.root).as_posix())
        if not matches:
            raise VaultError(f"unknown project id: {briefing_id}")
        return matches

    def copy_scope(self, paths: list[str], destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for relative in dict.fromkeys(paths):
            source = self.resolve_scoped_path(relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
