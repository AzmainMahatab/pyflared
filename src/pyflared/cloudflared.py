import asyncio
import os
import pathlib
import stat
import sys
from functools import cache
from importlib.abc import Traversable
from importlib.resources import files
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
def _bin_dir():
    # Bin directory lives inside the installed package
    return Path(__file__).resolve().parent / "bin"
    # return files('myapp.templates')


@cache
def _binary_filename() -> str:
    return "cloudflared" + ".exe" if os.name == "nt" else ""


# @cache
# def get_path() -> Path:
#     """
#     Return the absolute path to the bundled cloudflared binary.
#
#     Raises FileNotFoundError if the binary is not present.
#     """
#     path = _bin_dir() / _binary_filename()
#     if not path.exists():
#         file_children = [f.name for f in _bin_dir().iterdir() if f.is_file()]
#         raise FileNotFoundError(
#             f"Bundled cloudflared binary not found at {path}, only found: {file_children}. "
#             "This wheel is expected to include the binary. If you are building the wheel yourself, "
#             "use `hatch build` — the Hatch build hook will automatically bundle the latest upstream cloudflared."
#         )
#     return path
#
#
# @cache
# def get_path() -> Path:
#     """
#     Return the absolute path to the bundled cloudflared binary.
#
#     Raises FileNotFoundError if the binary is not present.
#     """
#     path = _bin_dir() / _binary_filename()
#     if not path.exists():
#         file_children = [f.name for f in _bin_dir().iterdir() if f.is_file()]
#         raise FileNotFoundError(
#             f"Bundled cloudflared binary not found at {path}, only found: {file_children}. "
#             "This wheel is expected to include the binary. If you are building the wheel yourself, "
#             "use `hatch build` — the Hatch build hook will automatically bundle the latest upstream cloudflared."
#         )
#     return path

def ensure_posix_executable(path: pathlib.Path) -> None:
    if os.name != "nt":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def get_files_recursively(entry: Traversable):
    """
    Recursively yield files from a Traversable object.
    works for both directories on disk and inside zips/wheels.
    """
    if entry.is_file():
        yield entry
    elif entry.is_dir():
        for child in entry.iterdir():
            # 'yield from' delegates to the recursive call
            yield from get_files_recursively(child)


def get_path() -> Path:
    # 1. Get the Traversable object
    root = files('pyflared')
    binary_ref = root / 'bin' / _binary_filename()

    # 2. Check if it's actually a real file on disk (Standard Install)
    # If this is False, it means you are in a Zip/Egg and MUST use as_file
    if isinstance(binary_ref, pathlib.Path):
        ensure_posix_executable(binary_ref)
        if not binary_ref.exists():
            children = [f.name for f in get_files_recursively(root)]
            raise FileNotFoundError(f"Bundled cloudflared binary not found at {binary_ref}. Bundled files: {children}")
        return binary_ref

    raise RuntimeError("Package is compressed! Cannot access binary path directly.")


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
