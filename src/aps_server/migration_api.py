"""Operator-only Vault archive export and approved migration import."""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import stat
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .api_support import ContentAPIError
from .atomic import write_text
from .config import Settings
from .extensions import ExtensionRegistry
from .vault import VaultError, VaultRepository


ARCHIVE_MANIFEST = ".aps-vault-archive.json"
MAX_ARCHIVE_FILES = 20_000
STANDARD_ROOTS = {
    "00_Inbox",
    "01_Ideas",
    "01_Idea_Sets",
    "02_Projects",
    "03_Services",
    "05_ProjectContexts",
    "99_Templates",
}


class ApplyMigrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(pattern=r"^migration_[A-F0-9]{24}$")


class MigrationError(RuntimeError):
    def __init__(self, message: str, code: str = "MIGRATION_INVALID") -> None:
        super().__init__(message)
        self.code = code


def build_migration_router(
    settings: Settings,
    vault: VaultRepository,
    extensions: ExtensionRegistry,
    authenticate: Callable[..., str],
) -> APIRouter:
    router = APIRouter(prefix="/v1/migration", tags=["migration"])
    root = (settings.data_path / "migration").resolve()
    exports = root / "exports"
    proposals = root / "proposals"

    def require_operator(role: str = Depends(authenticate)) -> str:
        if role != "operator":
            raise ContentAPIError(status.HTTP_403_FORBIDDEN, "OPERATION_FORBIDDEN", "Operator token required")
        if not extensions.is_installed("migration"):
            raise ContentAPIError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "EXTENSION_NOT_READY",
                "Migration extension is not installed",
            )
        return role

    @router.post("/exports")
    def create_export(_: str = Depends(require_operator)) -> dict[str, object]:
        try:
            with vault.locked():
                vault.require_clean()
                commit = vault.commit()
                export_id = "export_" + secrets.token_hex(12).upper()
                path = exports / f"{export_id}.zip"
                summary = _create_archive(vault.root, path, commit, settings.migration_max_archive_bytes)
            return {
                "export_id": export_id,
                "vault_commit": commit,
                "files": summary["files"],
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "download_url": f"/v1/migration/exports/{export_id}",
            }
        except (OSError, ValueError, MigrationError, VaultError) as error:
            _raise_migration(error)

    @router.get("/exports/{export_id}")
    def download_export(export_id: str, _: str = Depends(require_operator)) -> FileResponse:
        if not _valid_id(export_id, "export_"):
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "EXPORT_NOT_FOUND", "Export not found")
        path = exports / f"{export_id}.zip"
        if not path.is_file():
            raise ContentAPIError(status.HTTP_404_NOT_FOUND, "EXPORT_NOT_FOUND", "Export not found")
        return FileResponse(path, media_type="application/zip", filename=f"aps-vault-{export_id}.zip")

    @router.post("/imports", status_code=status.HTTP_201_CREATED)
    async def create_import(request: Request, _: str = Depends(require_operator)) -> dict[str, object]:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() not in {
            "application/zip",
            "application/octet-stream",
        }:
            raise ContentAPIError(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "ARCHIVE_MEDIA_TYPE_INVALID",
                "ZIP body required",
            )
        proposal_id = "migration_" + secrets.token_hex(12).upper()
        proposal_root = proposals / proposal_id
        archive = proposal_root / "upload.zip"
        extracted = proposal_root / "vault"
        try:
            proposal_root.mkdir(parents=True)
            size = await _save_body(request, archive, settings.migration_max_archive_bytes)
            summary = _extract_archive(archive, extracted, settings.migration_max_archive_bytes)
            with vault.locked():
                vault.require_clean()
                base_commit = vault.commit()
                proposal_commit, branch = _create_proposal(vault, extracted, proposal_id, base_commit, proposal_root)
            metadata = {
                "proposal_id": proposal_id,
                "status": "pending",
                "created_at": datetime.now(UTC).isoformat(),
                "base_commit": base_commit,
                "proposal_commit": proposal_commit,
                "branch": branch,
                "archive_bytes": size,
                **summary,
            }
            write_text(proposal_root / "proposal.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            return metadata
        except ContentAPIError:
            shutil.rmtree(proposal_root, ignore_errors=True)
            raise
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, MigrationError) as error:
            shutil.rmtree(proposal_root, ignore_errors=True)
            _raise_migration(error)

    @router.get("/imports/{proposal_id}")
    def get_import(proposal_id: str, _: str = Depends(require_operator)) -> dict[str, object]:
        return _load_proposal(proposals, proposal_id)

    @router.post("/imports/{proposal_id}/apply")
    def apply_import(
        proposal_id: str,
        body: ApplyMigrationRequest,
        _: str = Depends(require_operator),
    ) -> dict[str, object]:
        if body.confirmation != proposal_id:
            raise ContentAPIError(
                status.HTTP_409_CONFLICT,
                "MIGRATION_CONFIRMATION_INVALID",
                "Confirmation must match proposal ID",
            )
        metadata = _load_proposal(proposals, proposal_id)
        if metadata.get("status") != "pending":
            raise ContentAPIError(status.HTTP_409_CONFLICT, "MIGRATION_ALREADY_APPLIED", "Migration is not pending")
        proposal_root = proposals / proposal_id
        try:
            with vault.locked():
                vault.require_clean()
                if vault.commit() != metadata["base_commit"]:
                    raise MigrationError("Vault changed after proposal creation", "MIGRATION_BASE_CHANGED")
                backup_id = "export_" + secrets.token_hex(12).upper()
                backup_path = exports / f"{backup_id}.zip"
                _create_archive(vault.root, backup_path, vault.commit(), settings.migration_max_archive_bytes)
                vault._git("merge", "--ff-only", str(metadata["branch"]))
                _replace_inbox(vault.root, proposal_root / "vault" / "00_Inbox")
                if vault.push_after_commit:
                    vault.push()
                metadata.update(
                    status="applied",
                    applied_at=datetime.now(UTC).isoformat(),
                    vault_commit=vault.commit(),
                    backup_download_url=f"/v1/migration/exports/{backup_id}",
                )
                write_text(proposal_root / "proposal.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            return metadata
        except (OSError, ValueError, MigrationError, VaultError) as error:
            _raise_migration(error)

    return router


async def _save_body(request: Request, path: Path, maximum: int) -> int:
    size = 0
    with path.open("xb") as stream:
        async for chunk in request.stream():
            size += len(chunk)
            if size > maximum:
                raise MigrationError("Archive exceeds the configured size limit", "ARCHIVE_TOO_LARGE")
            stream.write(chunk)
    if size == 0:
        raise MigrationError("Archive body is empty")
    return size


def _create_archive(vault_root: Path, destination: Path, commit: str, maximum: int) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    total = 0
    try:
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(vault_root.rglob("*")):
                relative = path.relative_to(vault_root)
                if _excluded_vault_path(relative):
                    continue
                if path.is_symlink():
                    raise MigrationError(f"Vault contains a symbolic link: {relative.as_posix()}")
                if path.is_dir():
                    continue
                total += path.stat().st_size
                if total > maximum:
                    raise MigrationError("Vault exceeds the configured archive size limit", "ARCHIVE_TOO_LARGE")
                name = relative.as_posix()
                digest = _sha256(path)
                records.append({"path": name, "bytes": path.stat().st_size, "sha256": digest})
                archive.write(path, name)
            manifest = {
                "format": "aps-vault-archive",
                "version": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "source_commit": commit,
                "files": records,
            }
            archive.writestr(ARCHIVE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"files": len(records)}


def _extract_archive(archive_path: Path, destination: Path, maximum: int) -> dict[str, object]:
    destination.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise MigrationError("Archive contains too many files", "ARCHIVE_TOO_LARGE")
        if sum(member.file_size for member in members) > maximum:
            raise MigrationError("Expanded archive exceeds the configured size limit", "ARCHIVE_TOO_LARGE")
        names: set[str] = set()
        canonical_names: set[str] = set()
        for member in members:
            name = _safe_member(member)
            canonical = name.casefold()
            if name in names or canonical in canonical_names:
                raise MigrationError(f"Archive contains a duplicate path: {name}")
            names.add(name)
            canonical_names.add(canonical)
            if name == ARCHIVE_MANIFEST or member.is_dir():
                continue
            if _excluded_vault_path(Path(*PurePosixPath(name).parts)):
                continue
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
        manifest = _validate_manifest(archive, destination, names)
    if manifest == "external-zip":
        _flatten_wrapper(destination)
    roots = {path.relative_to(destination).parts[0] for path in destination.rglob("*") if path != destination}
    if not roots.intersection(STANDARD_ROOTS) and not {"README.md", "AGENTS.md"}.intersection(roots):
        raise MigrationError("Archive does not look like an APS Vault")
    return {"files": sum(path.is_file() for path in destination.rglob("*")), "source": manifest}


def _safe_member(member: zipfile.ZipInfo) -> str:
    path = PurePosixPath(member.filename.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise MigrationError(f"Archive path is unsafe: {member.filename}")
    if path.parts[0].casefold() == ".git":
        raise MigrationError("Archive must not contain Git repository data")
    for part in path.parts:
        if len(part.encode("utf-8")) > 255 or part[-1:] in {" ", "."}:
            raise MigrationError(f"Archive path is not portable: {member.filename}")
        if any(ord(char) < 32 or char in '<>:"|?*' for char in part):
            raise MigrationError(f"Archive path is not portable: {member.filename}")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise MigrationError(f"Archive contains a symbolic link: {member.filename}")
    return path.as_posix().rstrip("/")


def _validate_manifest(archive: zipfile.ZipFile, destination: Path, names: set[str]) -> str:
    if ARCHIVE_MANIFEST not in names:
        return "external-zip"
    try:
        manifest = json.loads(archive.read(ARCHIVE_MANIFEST))
        if manifest.get("format") != "aps-vault-archive" or manifest.get("version") != 1:
            raise MigrationError("Archive manifest version is unsupported")
        expected = {item["path"]: item["sha256"] for item in manifest["files"]}
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationError("Archive manifest is invalid") from error
    actual = {
        path.relative_to(destination).as_posix(): _sha256(path)
        for path in destination.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise MigrationError("Archive file list or checksum does not match its manifest")
    return "aps-vault-archive-v1"


def _flatten_wrapper(destination: Path) -> None:
    children = list(destination.iterdir())
    if len(children) != 1 or not children[0].is_dir():
        return
    wrapper = children[0]
    wrapper_names = {item.name for item in wrapper.iterdir()}
    if not wrapper_names.intersection(STANDARD_ROOTS) and not {"README.md", "AGENTS.md"}.intersection(wrapper_names):
        return
    temporary = destination.parent / f".{destination.name}-flattened"
    temporary.mkdir()
    for item in wrapper.iterdir():
        item.replace(temporary / item.name)
    shutil.rmtree(destination)
    temporary.replace(destination)


def _create_proposal(
    vault: VaultRepository,
    source: Path,
    proposal_id: str,
    base_commit: str,
    proposal_root: Path,
) -> tuple[str, str]:
    worktree = proposal_root / "worktree"
    branch = f"aps-migration/{proposal_id}"
    vault._git("worktree", "add", "--detach", str(worktree), base_commit)
    try:
        for item in worktree.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in source.iterdir():
            if item.name == "00_Inbox":
                continue
            target = worktree / item.name
            shutil.copytree(item, target) if item.is_dir() else shutil.copy2(item, target)
        _run_git(worktree, "add", "-A")
        _run_git(
            worktree,
            "-c",
            "user.name=APS Server",
            "-c",
            "user.email=aps-server@localhost",
            "commit",
            "--allow-empty",
            "-m",
            f"vault: apply migration {proposal_id}",
        )
        ignored = _run_git(worktree, "status", "--ignored", "--porcelain", "--untracked-files=all")
        if ignored:
            raise MigrationError("Archive contains files ignored by its own .gitignore", "ARCHIVE_IGNORED_FILE")
        commit = _run_git(worktree, "rev-parse", "HEAD")
        vault._git("branch", branch, commit)
        return commit, branch
    finally:
        if worktree.exists():
            shutil.rmtree(worktree)
        vault._git("worktree", "prune")


def _replace_inbox(vault_root: Path, source: Path) -> None:
    target = vault_root / "00_Inbox"
    replacement = vault_root / ".migration-inbox"
    shutil.rmtree(replacement, ignore_errors=True)
    if source.is_dir():
        shutil.copytree(source, replacement)
    else:
        replacement.mkdir()
    shutil.rmtree(target, ignore_errors=True)
    replacement.replace(target)


def _excluded_vault_path(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return False
    root = parts[0]
    if root in {".git", ".brief", ".ssh", "tasks"}:
        return True
    if root == ".env" or root.startswith(".env."):
        return True
    if relative.as_posix() in {".aps.local.json", ".git-credentials"}:
        return True
    return relative.as_posix() in {".obsidian/workspace.json", ".obsidian/workspace-mobile.json"}


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
        raise MigrationError(completed.stderr.strip() or "Git proposal operation failed", "MIGRATION_GIT_FAILED")
    return completed.stdout.strip()


def _load_proposal(root: Path, proposal_id: str) -> dict[str, object]:
    if not _valid_id(proposal_id, "migration_"):
        raise ContentAPIError(status.HTTP_404_NOT_FOUND, "MIGRATION_NOT_FOUND", "Migration proposal not found")
    path = root / proposal_id / "proposal.json"
    if not path.is_file():
        raise ContentAPIError(status.HTTP_404_NOT_FOUND, "MIGRATION_NOT_FOUND", "Migration proposal not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_id(value: str, prefix: str) -> bool:
    suffix = value.removeprefix(prefix)
    return value.startswith(prefix) and len(suffix) == 24 and all(char in "0123456789ABCDEF" for char in suffix)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raise_migration(error: Exception) -> None:
    code = error.code if isinstance(error, MigrationError) else "MIGRATION_FAILED"
    status_code = status.HTTP_409_CONFLICT
    if code == "ARCHIVE_TOO_LARGE":
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif code in {"MIGRATION_INVALID", "ARCHIVE_IGNORED_FILE"}:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise ContentAPIError(status_code, code, str(error)) from error
