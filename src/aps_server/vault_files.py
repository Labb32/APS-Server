"""Safe file reads for content originating in a Git-backed Vault."""

from __future__ import annotations

from pathlib import Path


MAX_VAULT_DOCUMENT_BYTES = 2 * 1024 * 1024


class UnsafeVaultPathError(OSError):
    pass


def require_vault_file(vault_root: Path, path: Path) -> Path:
    root = vault_root.resolve()
    if path.is_symlink():
        raise UnsafeVaultPathError(f"Vault symlink is not allowed: {path.name}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise UnsafeVaultPathError(f"Vault file escapes its root: {path.name}") from error
    if not resolved.is_file():
        raise UnsafeVaultPathError(f"Vault path is not a regular file: {path.name}")
    if resolved.stat().st_size > MAX_VAULT_DOCUMENT_BYTES:
        raise UnsafeVaultPathError(f"Vault file exceeds the size limit: {path.name}")
    return resolved


def read_vault_text(vault_root: Path, path: Path) -> str:
    return require_vault_file(vault_root, path).read_text(encoding="utf-8-sig")


def read_vault_bytes(vault_root: Path, path: Path) -> bytes:
    return require_vault_file(vault_root, path).read_bytes()
