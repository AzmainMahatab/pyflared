import asyncio
import atexit
import os
import pathlib
import stat
import sys
from contextlib import ExitStack
from functools import cache
from importlib.resources import files, as_file
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Iterator

import argparse
import typer
from pyflared.binary.binary import BinaryWrapper
from pyflared.binary.process import ProcessContext
from pyflared.tunnel import TunnelManager
from pyflared.typealias import Mappings, ProcessArgs

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


def _ensure_posix_executable(path: pathlib.Path) -> None:
    if os.name != "nt":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _get_files_recursively(entry: Traversable) -> Iterator[Traversable]:
    """
    Recursively yield full string paths from a Traversable object.
    Works for both directories on disk and inside zips/wheels.
    """
    if entry.is_dir():
        for child in entry.iterdir():
            yield from _get_files_recursively(child)
    else:
        yield entry


_file_manager = ExitStack()
atexit.register(_file_manager.close)


@cache
def get_path() -> pathlib.Path:
    # 1. Get package root
    root = files(__package__)
    binary_ref = root / 'bin' / _binary_filename()

    # 2. "Mount" the file
    # This guarantees 'path' is a real file system path (original or temp extracted).
    path = _file_manager.enter_context(as_file(binary_ref))

    # 3. Validation (Now we treat it as a standard file)
    if not path.exists():
        # Debugging helper: List what IS there to help solve the error
        children = list(_get_files_recursively(root))
        raise FileNotFoundError(
            f"Bundled binary not found at: {path}\nAvailable files: {children}"
        )

    # 5. Permissions (Linux/Mac specific)
    _ensure_posix_executable(path)

    return path


cloudflared_binary = BinaryWrapper(get_path())

token_tunnel_cmd: ProcessArgs = "tunnel", "run", "--token"
quick_tunnel_cmd: ProcessArgs = "tunnel", "--no-autoupdate", "--url"


def run_token_tunnel(token: str) -> ProcessContext:
    return cloudflared_binary.execute_streaming_response(*token_tunnel_cmd, token)


def run_quick_tunnel(service: str):
    return cloudflared_binary.execute_streaming_response(*quick_tunnel_cmd, service)


def run_dns_fixed_tunnel(mappings: Mappings, api_token: str | None = None):
    async def tunnel_token_cmd() -> ProcessArgs:
        tunnel_manager = TunnelManager(api_token)
        await tunnel_manager.remove_orphans()
        tunnel_token = await tunnel_manager.fixed_dns_tunnel(mappings)
        cmd = token_tunnel_cmd + (tunnel_token.__str__(),)
        return cmd

    return cloudflared_binary.execute_streaming_response_from_async(tunnel_token_cmd)


async def version():
    result = await cloudflared_binary.execute_await_response("version")
    if result.return_code != 0:
        raise ValueError("Version not found")
    return result.stdout

# tunnel id or name
# async def tunnel_dns_create(tunnel: str, domain: str):
#     result = await cloudflared_binary.execute_await_response(
#         "tunnel", "route", "dns", tunnel, domain
#     )
#     if result.return_code != 0:
#         raise ValueError(f"{result.stderr}")
#     return result.stdout
