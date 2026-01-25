import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Final, NoReturn

import pyflared
import typer
from loguru import logger
from pydantic import SecretStr
from pyflared import IS_WINDOWS, binary_path
from pyflared._commands import Mapping
from pyflared.cli.tunnel import pretty_tunnel_status
from pyflared.log.config import isolated_logging
from pyflared.ssh.config import SSHConfig
from pyflared.ssh.exists import check_sshd_status, SshdStatus
from pyflared.utils.pydantic_parse import pydantic_typer_parse

ssh_subcommand = typer.Typer(help="Cloudflared ssh")

SSH_DIR: Final[Path] = Path.home() / ".ssh"
CONFIG_FILE: Final[Path] = SSH_DIR / "config"
INCLUDE_DIRECTIVE: Final[str] = "Include pyflared/*.conf"


def _secure_path_windows(path: Path) -> None:
    """
    Secures a file OR directory on Windows using native 'icacls'.

    1. Disables inheritance (/inheritance:r)
    2. Grants Full Control ONLY to the current user (/grant:r <user>:(F))
    3. Removes all other access (implicit in the /inheritance:r + /grant:r combo)

    This satisfies OpenSSH's strict permission requirements without
    needing external dependencies like 'pywin32'.
    """
    path_str = str(path)
    username = os.getlogin()

    # Build command parts
    # /T = Apply recursively (useful if securing a directory)
    # /C = Continue on error (robustness)
    # /Q = Quiet (suppress success messages)
    cmd = [
        "icacls",
        path_str,
        "/inheritance:r",
        "/grant:r",
        f"{username}:(F)",
        "/T",
        "/C",
        "/Q"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode().strip()
        raise RuntimeError(f"Failed to secure permissions for {path}: {error_msg}") from e


def _ensure_correct_permission(file: Path):
    if IS_WINDOWS:
        _secure_path_windows(file)
    elif file.is_dir():
        file.chmod(0o700)  # rwx------
    else:
        file.chmod(0o600)  # rw-------


def _ensure_ssh_config() -> None:
    """
    Ensures ~/.ssh/config exists, includes the pyflared directive,
    and has secure permissions on both Windows and POSIX systems.
    """

    # --- Step 1: Secure the Directory ---
    if not SSH_DIR.exists():
        logger.info(f".ssh dir is missing, creating .ssh directory at {SSH_DIR}...")
        SSH_DIR.mkdir(parents=True, exist_ok=True)

        # Immediately lock down the folder
        _ensure_correct_permission(SSH_DIR)

    # --- Step 2: Check Existing Config ---
    current_content = ""
    if CONFIG_FILE.exists():
        current_content = CONFIG_FILE.read_text(encoding="utf-8")
        if current_content.startswith(INCLUDE_DIRECTIVE):
            logger.debug("SSH config already configured")
            return

    logger.info(f"Adding pyflared directive at {CONFIG_FILE}...")

    other_config = (line for line in current_content if line.strip() != INCLUDE_DIRECTIVE)

    # --- Step 3: Prepare Content ---
    # Prepend to top to ensure priority
    new_content = f"{INCLUDE_DIRECTIVE}\n" + "\n".join(other_config) + "\n"

    # --- Step 4: Atomic Write & Secure ---
    # We write to a temp file first to avoid corrupting the real config if the script crashes
    temp_file = CONFIG_FILE.with_suffix(".tmp")

    try:
        temp_file.write_text(new_content, encoding="utf-8")

        # Apply permissions to the temp file BEFORE it becomes the real config
        _ensure_correct_permission(temp_file)

        # Atomic Move: This overwrites the target file instantly
        temp_file.replace(CONFIG_FILE)
        logger.info("Success: ~/.ssh/config updated and secured.")

    except Exception as e:
        # Cleanup temp file on failure
        if temp_file.exists():
            temp_file.unlink()
        raise e


def _upsert_config(ssh_config: SSHConfig) -> None:
    # 1. Ensure the Include directive exists in ~/.ssh/config
    _ensure_ssh_config()

    conf_dir: Path = SSH_DIR / "pyflared"
    target_file: Path = conf_dir / f"{ssh_config.filename}.conf"

    # Render content once
    expected_content: str = ssh_config.config_text()

    # 2. Secure Directory Lifecycle
    # We ensure the container directory exists and is locked down
    # BEFORE we attempt to write any sensitive files into it.
    if not conf_dir.exists():
        conf_dir.mkdir(parents=True, exist_ok=True)

        # Apply strict permissions to the folder itself
        _ensure_correct_permission(conf_dir)

    # 3. Idempotency Check (Performance Hack)
    # If file exists and content matches bit-for-bit, return immediately.
    if target_file.exists():
        try:
            # Always specify encoding to avoid Windows locale issues
            if target_file.read_text(encoding="utf-8") == expected_content:
                return
        except (OSError, UnicodeDecodeError):
            # If file is unreadable or corrupted, proceed to overwrite it.
            pass

    # 4. Atomic Write & Secure
    # We write to a .tmp file, secure it, then rename it.
    temp_file: Path = target_file.with_suffix(".tmp")

    try:
        temp_file.write_text(expected_content, encoding="utf-8")

        # Apply permissions to the file content
        _ensure_correct_permission(temp_file)

        # Atomic Replace (Authority Enforcement)
        # This overwrites the target if it exists, or creates it if it doesn't.
        temp_file.replace(target_file)

        logger.info(f"Refreshed config for {ssh_config.alias}")

    except Exception as e:
        # Cleanup garbage if the operation failed
        if temp_file.exists():
            temp_file.unlink()
        raise e


@ssh_subcommand.command()
@pydantic_typer_parse
def add(ssh_config: SSHConfig):
    _upsert_config(ssh_config)


@ssh_subcommand.command()
def remove(alias: str):
    # Deleting is just removing a file
    config_file = SSH_DIR / "pyflared" / f"{alias}.conf"

    if config_file.exists():
        config_file.unlink()
        typer.echo(f"Removed config for alias: {alias}")
    else:
        typer.echo(f"No config found for {alias}", err=True)


@ssh_subcommand.command()
# We accept a tuple of args to handle "user@host -v -p 22" naturally
def connect(ssh_args: list[str]) -> NoReturn:
    """
    Handles ssh args naturally in pyflared
    Example usage: pyflared ssh connect user@ssh.yoursite.com

    Args:
        ssh_args: The target hostname to connect to.
    """
    cloudflared_bin = binary_path()

    # 1. Quote the binary path to be safe against spaces
    # We use single quotes for the inner path so the shell reads it as one unit.
    proxy_cmd = f"'{cloudflared_bin}' access ssh --hostname %h"

    # 2. Construct the Arguments
    # We combine our forced config with whatever the user typed.
    final_args = [
        "ssh",
        "-o", f"ProxyCommand={proxy_cmd}",
        *ssh_args  # Unpack the tuple: ("user@host", "-v") -> "user@host", "-v"
    ]

    sys.stdout.flush()
    sys.stderr.flush()

    try:
        # Use execvp to find 'ssh' in PATH automatically
        os.execvp("ssh", final_args)
    except OSError as e:
        typer.echo(f"Execution failed: {e}", err=True)
        sys.exit(e.errno)


@ssh_subcommand.command()
def proxy(hostname: str) -> NoReturn:
    """
    Example usage: ssh -o ProxyCommand="pyflared ssh proxy %h" user@ssh.yoursite.com

    Args:
        hostname: The target hostname to connect to.
    """

    args = [
        "cloudflared",  # argv[0]: The program name (convention)
        "access",
        "ssh",
        "--hostname",
        hostname
    ]

    # Process Replacement
    # This call never returns. The OS overlays 'cloudflared' onto this PID.
    # Python memory is freed immediately.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execv(binary_path(), args)
    except OSError as e:
        typer.echo(f"Execution failed: {e}", err=True)
        sys.exit(e.errno)


@ssh_subcommand.command()
def serve(
        hostname: str = typer.Argument(
            ...,
            metavar="example.co,",  # Changes display in usage synopsis
            help="Domain where you want to serve SSH",
            show_default=False
        ),
        tunnel_name: str | None = typer.Option(
            None, "--tunnel-name", "-n",
            help="Tunnel name",
            show_default="hostname_YYYY-MM-DD_UTC..."
        ),
        keep_orphans: bool = typer.Option(
            False,
            "--keep-orphans",
            "-k",
            help="Preserve orphan tunnels (prevents default removal)."
        ),
        api_token: SecretStr | None = typer.Option(
            None,
            envvar="CLOUDFLARE_API_TOKEN",
            parser=SecretStr,
            help="Cloudflare API Token to manage tunnels and dns",  # TODO: specify token needed permission
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs"),
):
    sshd_status = check_sshd_status()
    match sshd_status:
        case SshdStatus.BINARY_MISSING:
            logger.warning("❌ SSH Server is NOT INSTALLED.")  # TODO: provide link to installation guide
        case SshdStatus.NOT_RUNNING:
            logger.warning("⚠️  SSH Server is INSTALLED but NOT RUNNING.")  # TODO: provide link to start guide

    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        pairs = Mapping.from_pair(hostname, "ssh://localhost:22")

        tunnel = pyflared.run_dns_fixed_tunnel(
            [pairs], api_token=api_token.get_secret_value(), remove_orphan=not keep_orphans,
            tunnel_name=tunnel_name)  # TODO: pass remove_orphan
        asyncio.run(tunnel.start_background([pretty_tunnel_status]))
