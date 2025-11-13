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
            "This wheel is expected to include the binary. If you are building the wheel yourself, "
            "use `hatch build` — the Hatch build hook will automatically bundle the latest upstream cloudflared."
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


def version():
    return main(["--version"])


if __name__ == "__main__":
    raise SystemExit(main())
