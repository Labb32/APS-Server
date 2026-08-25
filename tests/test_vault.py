import subprocess
from pathlib import Path

import pytest

from aps_server.vault import VaultError, VaultRepository


def git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()


def configure(path: Path) -> None:
    git(path, "config", "user.email", "aps-test@example.invalid")
    git(path, "config", "user.name", "APS Test")


def make_remote(tmp_path: Path) -> tuple[Path, Path, Path]:
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    server = tmp_path / "server"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
    configure(seed)
    (seed / "README.md").write_text("initial", encoding="utf-8")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "initial")
    git(seed, "push", "-u", "origin", "main")
    subprocess.run(["git", "clone", str(remote), str(server)], check=True, capture_output=True)
    configure(server)
    return remote, seed, server


def test_sync_fast_forwards(tmp_path):
    _, seed, server = make_remote(tmp_path)
    (seed / "remote.md").write_text("new", encoding="utf-8")
    git(seed, "add", "remote.md")
    git(seed, "commit", "-m", "remote update")
    git(seed, "push")

    commit = VaultRepository(server).sync()

    assert commit == git(seed, "rev-parse", "HEAD")
    assert (server / "remote.md").read_text(encoding="utf-8") == "new"


def test_sync_refuses_dirty_worktree(tmp_path):
    _, _, server = make_remote(tmp_path)
    (server / "README.md").write_text("dirty", encoding="utf-8")

    with pytest.raises(VaultError, match="dirty"):
        VaultRepository(server).sync()


def test_sync_refuses_diverged_history(tmp_path):
    _, seed, server = make_remote(tmp_path)
    (server / "local.md").write_text("local", encoding="utf-8")
    git(server, "add", "local.md")
    git(server, "commit", "-m", "local update")
    (seed / "remote.md").write_text("remote", encoding="utf-8")
    git(seed, "add", "remote.md")
    git(seed, "commit", "-m", "remote update")
    git(seed, "push")

    with pytest.raises(VaultError, match="fast-forwarded"):
        VaultRepository(server).sync()
