"""Operator-only interactive setup for persistent container Git credentials."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def _auth_home() -> Path:
    home = Path(os.environ.get("HOME", "/git-auth")).resolve()
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)
    return home


def _configure_store() -> None:
    credentials = _auth_home() / "credentials"
    subprocess.run(
        ["git", "config", "--global", "credential.helper", f"store --file {credentials}"],
        check=True,
    )


def login_http(remote_url: str, username: str | None) -> None:
    parsed = urlsplit(remote_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("remote must be an HTTP(S) URL without embedded credentials")
    user = username or input("Git username: ").strip()
    secret = getpass.getpass("Personal access token/password: ")
    if not user or not secret:
        raise SystemExit("username and credential are required")
    _configure_store()
    subprocess.run(
        ["git", "credential", "approve"],
        input=f"protocol={parsed.scheme}\nhost={parsed.netloc}\nusername={user}\npassword={secret}\n\n",
        text=True,
        check=True,
    )
    credential_path = _auth_home() / "credentials"
    credential_path.chmod(0o600)
    print(f"Stored {parsed.scheme.upper()} Git credential for {parsed.netloc} in the persistent auth volume.")


def init_ssh(host: str, port: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise SystemExit("host must be a DNS name or IPv4 address")
    ssh = _auth_home() / ".ssh"
    ssh.mkdir(parents=True, exist_ok=True)
    ssh.chmod(0o700)
    private_key = ssh / "id_ed25519"
    if not private_key.exists():
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key), "-C", "aps-server"],
            check=True,
        )
    scan = subprocess.run(
        ["ssh-keyscan", "-p", str(port), "-H", host],
        capture_output=True,
        text=True,
        check=True,
    )
    scanned_fingerprints = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=scan.stdout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"Scanned SSH host-key fingerprints for {host}:{port}:\n{scanned_fingerprints}\n")
    if input("Store these host keys? Type 'yes' after independent verification: ").strip() != "yes":
        raise SystemExit("host keys were not stored")
    known_hosts = ssh / "known_hosts"
    existing = known_hosts.read_text(encoding="utf-8") if known_hosts.exists() else ""
    additions = "".join(line + "\n" for line in scan.stdout.splitlines() if line and line not in existing)
    if additions:
        with known_hosts.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(additions)
    private_key.chmod(0o600)
    known_hosts.chmod(0o600)
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub"))],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print("Register this public key with the Git service:\n")
    print(private_key.with_suffix(".pub").read_text(encoding="utf-8").strip())
    print(f"\nLocal key fingerprint: {fingerprint}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure persistent APS Git authentication")
    subparsers = parser.add_subparsers(dest="command", required=True)
    login = subparsers.add_parser("login-http", help="store one HTTP(S) Git credential interactively")
    login.add_argument("remote_url")
    login.add_argument("--username")
    ssh = subparsers.add_parser("init-ssh", help="create a persistent SSH key and remember one Git host")
    ssh.add_argument("host")
    ssh.add_argument("--port", type=int, default=22, choices=range(1, 65536), metavar="PORT")
    args = parser.parse_args()
    if args.command == "login-http":
        login_http(args.remote_url, args.username)
    elif args.command == "init-ssh":
        init_ssh(args.host, args.port)


if __name__ == "__main__":
    main()
