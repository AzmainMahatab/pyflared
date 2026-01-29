import platform
import shutil
import socket
from enum import StrEnum, auto
from pathlib import Path

from pyflared.shared.consts import IS_WINDOWS


def is_sshd_running(host: str = "localhost", port: int = 22, timeout: float = 1.0) -> bool:
    """
    Checks if the SSH server is actively listening on the given port.
    """
    try:
        # Try to open a TCP connection to localhost:22
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


def is_sshd_installed() -> bool:
    """
    Checks if the SSH Server binary exists on the system.
    """
    system = platform.system()

    if system == "Windows":
        # Windows 10/11 installs OpenSSH here by default
        default_path = Path("C:/Windows/System32/OpenSSH/sshd.exe")
        if default_path.exists():
            return True
        # Fallback: Check if recognized in PATH
        return shutil.which("sshd") is not None

    # Linux & macOS
    # Common locations for sshd on Unix
    search_paths = [
        "/usr/sbin/sshd",
        "/usr/bin/sshd",
        "/sbin/sshd",
        "/usr/local/sbin/sshd"
    ]

    # 1. Check strict paths first
    for path in search_paths:
        if Path(path).exists():
            return True

    # 2. Check globally in PATH (less likely to work for non-root, but worth a try)
    if shutil.which("sshd"):
        return True

    # 3. macOS specific check (it's built-in, so it's technically always "installed")
    if system == "Darwin":
        return True

    return False


class SshdStatus(StrEnum):
    BINARY_MISSING = auto()
    NOT_RUNNING = auto()
    RUNNING = auto()


def check_sshd_status():
    if is_sshd_running():
        return SshdStatus.RUNNING
    if is_sshd_installed():
        return SshdStatus.NOT_RUNNING
    return SshdStatus.BINARY_MISSING


def is_ssh_client_installed() -> bool:
    """
    Checks if the SSH Client ('ssh') is available on the system.

    Returns:
        bool: True if the client is found in PATH or standard locations, False otherwise.
    """
    # 1. Standard Check: Look for 'ssh' in the system PATH.
    # This works for Linux, macOS, and correctly configured Windows.
    if shutil.which("ssh") is not None:
        return True

    # 2. Windows Fallback:
    # Sometimes 'System32/OpenSSH' is not in the user's PATH variable,
    # even if installed by default on Windows 10/11.
    if IS_WINDOWS:
        default_windows_path = Path("C:/Windows/System32/OpenSSH/ssh.exe")
        if default_windows_path.exists():
            return True

    return False
