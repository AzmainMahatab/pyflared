import os
import sys
import stat
import subprocess
from typing import List
from pathlib import Path

# Public API
__all__ = ["get_path", "main", "version"]


def _bin_dir() -> Path:
    # Bin directory lives inside the installed package
    return Path(__file__).resolve().parent / "bin"


def _binary_filename() -> str:
    # We always name the embedded binary consistently at build time
    return "cloudflared" + ".exe" if os.name == "nt" else ""


def get_path() -> str:
    """
    Return the absolute path to the bundled cloudflared binary.

    Raises FileNotFoundError if the binary is not present.
    """
    path = _bin_dir() / _binary_filename()
    if not path.exists():
        raise FileNotFoundError(
            f"Bundled cloudflared binary not found at {path}. "
            "Install the package (non-editable) so the wheel's bin/ is available, or build and install the wheel."
        )
    # Ensure executable bit on POSIX
    if os.name != "nt":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def main(argv: List[str] | None = None) -> int:
    """
    Console entry point that proxies all arguments to the bundled binary.
    """
    if argv is None:
        argv = sys.argv[1:]
    binary = get_path()
    # Use subprocess that inherits stdin/stdout/stderr
    try:
        proc = subprocess.Popen([binary, *argv])
        return proc.wait()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        return 130


def version() -> str:
    """
    Return the cloudflared version string by invoking the binary with --version.
    """
    binary = get_path()
    # Capture stdout; cloudflared prints version to stdout and may include extra info
    try:
        completed = subprocess.run([binary, "--version"], check=True, capture_output=True, text=True)
        out = (completed.stdout or "").strip()
        # Return first line to keep it succinct
        return out.splitlines()[0] if out else ""
    except subprocess.CalledProcessError as e:
        # Include stderr if available to aid debugging
        msg = (e.stdout or "" + e.stderr or "").strip()
        raise RuntimeError(f"cloudflared --version failed: {msg}") from e


if __name__ == "__main__":
    raise SystemExit(main())
