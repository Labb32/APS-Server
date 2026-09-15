"""Container bootstrap for Vault provisioning and official extensions."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .agent.providers import provider_status
from .config import Settings
from .extensions import OfficialExtensionInstaller


class BootstrapError(RuntimeError):
    pass


_ENV_KEY = re.compile(r"^APS_[A-Z0-9_]+$")


def load_config_file() -> None:
    configured = os.environ.get("APS_CONFIG_FILE", "").strip()
    if not configured:
        return
    path = Path(configured)
    if not path.is_file():
        raise BootstrapError(f"APS_CONFIG_FILE does not exist: {path}")
    for number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise BootstrapError(f"invalid config line {number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY.fullmatch(key):
            raise BootstrapError(f"invalid config key on line {number}: {key}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise BootstrapError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _require_empty(path: Path) -> None:
    if any(path.iterdir()):
        raise BootstrapError(f"Vault target is not empty and is not a Git repository: {path}")


def _copy_template(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise BootstrapError(f"built-in Vault template is missing: {source}")
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _trust_local_clone_source(source: str) -> None:
    """Trust only an explicitly configured absolute local clone source.

    Container bind mounts often have a different owner.  Remote URLs never
    reach this path and callers cannot supply arbitrary Git configuration.
    """
    path = Path(source)
    if not path.is_absolute():
        return
    safe_repository = (path.resolve() / ".git").as_posix()
    completed = subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", safe_repository],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise BootstrapError(f"could not trust local Git source {safe_repository}: {detail}")


def prepare_vault(settings: Settings) -> None:
    root = settings.vault_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    repository = root / ".git"

    if settings.vault_mode == "local":
        if not repository.exists():
            _require_empty(root)
            _copy_template(settings.vault_template_path.resolve(), root)
            _run_git(root, "init", "-b", "main")
            _run_git(root, "add", ".")
            _run_git(
                root,
                "-c", "user.name=APS Server", "-c", "user.email=aps-server@localhost",
                "commit", "-m", "vault: initialize APS template",
            )
        os.environ["APS_SYNC_BEFORE_JOB"] = "false"
        return

    if settings.vault_mode == "mounted":
        if not repository.exists():
            raise BootstrapError(f"mounted Vault is not a Git repository: {root}")
        return

    if not settings.vault_git_url or not settings.vault_git_url.strip():
        raise BootstrapError("APS_VAULT_GIT_URL is required when APS_VAULT_MODE=git")
    expected_url = settings.vault_git_url.strip()
    if not repository.exists():
        _require_empty(root)
        _trust_local_clone_source(expected_url)
        command = ["clone"]
        if settings.vault_git_branch:
            command.extend(["--branch", settings.vault_git_branch, "--single-branch"])
        command.extend([expected_url, "."])
        _run_git(root, *command)
    actual_url = _run_git(root, "remote", "get-url", "origin")
    if actual_url != expected_url:
        raise BootstrapError("existing Vault origin does not match APS_VAULT_GIT_URL")


def prepare_git_auth() -> None:
    """Keep non-interactive Git authentication in its persistent volume."""
    home = Path(os.environ.get("HOME", "/git-auth")).resolve()
    ssh = home / ".ssh"
    ssh.mkdir(parents=True, exist_ok=True)
    ssh.chmod(0o700)
    credentials = home / "credentials"
    if credentials.exists():
        credentials.chmod(0o600)
    completed = subprocess.run(
        ["git", "config", "--global", "credential.helper", f"store --file {credentials}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise BootstrapError("could not configure persistent Git credentials")


def prepare_extensions(settings: Settings) -> None:
    installer = OfficialExtensionInstaller(settings.official_extensions_path, settings.extensions_path)
    for extension_id in settings.requested_extensions:
        try:
            installer.install(extension_id)
        except KeyError as error:
            raise BootstrapError(f"unknown official initial extension: {extension_id}") from error


def require_ai_provider(settings: Settings) -> None:
    configured, status = provider_status(settings)
    if configured:
        return
    provider = status["provider"]
    raise BootstrapError(f"selected AI provider is not ready: {provider}")


def main() -> None:
    load_config_file()
    settings = Settings()
    require_ai_provider(settings)
    prepare_git_auth()
    prepare_vault(settings)
    prepare_extensions(settings)
    os.execvp(
        "uvicorn",
        [
            "uvicorn", "aps_server.main:app",
            "--host", settings.http_host,
            "--port", str(settings.http_port),
            "--workers", "1",
        ],
    )


if __name__ == "__main__":
    main()
