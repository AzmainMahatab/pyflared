# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "rich",
# ]
# ///

import glob
import os
import subprocess
import sys
from typing import NoReturn

from rich.console import Console

err_console = Console(stderr=True)


def fail(msg: str, code: int = 1) -> NoReturn:
    """Print error and exit."""
    err_console.print(f"❌ {msg}")
    sys.exit(code)


def run_build() -> None:
    # 1. Check Env Var
    use_prebuilt: bool = os.environ.get("USE_PREBUILT_WHEEL", "false").lower() == "true"

    if use_prebuilt:
        err_console.print("🔹 MODE: PRE-BUILT ARTIFACT DETECTED")
        # Check for existence of any wheel file
        if not glob.glob("dist/*.whl"):
            fail("No .whl files found in dist/.")
        err_console.print("✅ Valid artifact found.")

    else:
        err_console.print("🔸 MODE: BUILD FROM SOURCE")
        try:
            subprocess.run(
                [sys.executable, "-m", "hatch", "build"],
                check=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            fail(f"Build failed with exit code {e.returncode}")
        except FileNotFoundError:
            fail("Hatch binary not found. Is it installed?")


if __name__ == "__main__":
    run_build()
