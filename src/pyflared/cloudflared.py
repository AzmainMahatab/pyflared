import asyncio
import os
import stat
import sys
from functools import cache
from pathlib import Path

from pyflared.binary.binary import BinaryWrapper
from pyflared.binary.process import ProcessContext
from pyflared.tunnel import TunnelManager
from pyflared.typealias import Mappings

__all__ = ["cloudflared_binary", "run_token_tunnel", "run_quick_tunnel", "version"]


# class CloudflareBinary(_BinaryWrapper):
#     def __init__(self):
#         super().__init__(get_path())
# def tunnel(token: str):
#     return _ServiceContext(get_path(), "tunnel", "run", "--token", token)

@cache
def _bin_dir() -> Path:
    # Bin directory lives inside the installed package
    return Path(__file__).resolve().parent / "bin"


@cache
def _binary_filename() -> str:
    return "cloudflared" + ".exe" if os.name == "nt" else ""


@cache
def get_path() -> Path:
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
    return path


cloudflared_binary = BinaryWrapper(get_path())

token_tunnel_cmd = "tunnel", "run", "--token"
quick_tunnel_cmd = "tunnel", "--no-autoupdate", "--url"


def run_token_tunnel(token: str) -> ProcessContext:
    return cloudflared_binary.execute_streaming_response(*token_tunnel_cmd, token)


def run_quick_tunnel(service: str):
    return cloudflared_binary.execute_streaming_response(*quick_tunnel_cmd, service)


def run_dns_fixed_tunnel(api_token: str, mappings: Mappings):
    async def tunnel_token_cmd() -> tuple[str, ...]:
        tunnel_manager = TunnelManager(api_token)
        await tunnel_manager.remove_orphans()
        tunnel_token = await tunnel_manager.fixed_dns_tunnel(mappings)
        cmd = token_tunnel_cmd + (tunnel_token.__str__(),)
        return cmd

    return cloudflared_binary.execute_streaming_response_from_async(tunnel_token_cmd)


async def version():
    result = await cloudflared_binary.execute_await_response("--version")
    if result.return_code != 0:
        raise ValueError("Version not found")
    return result.stdout


async def main(*args: str):
    if args is None:
        args = sys.argv[1:]
    return await cloudflared_binary.execute_streaming_response(*args).start_background()


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

# async def version() -> str:
#     async with _ServiceContext(get_path(), "--version") as service:
#         async for event in service:
#             if isinstance(event, StdOut):
#                 return event.line.strip()
#     raise ValueError("Version not found")
