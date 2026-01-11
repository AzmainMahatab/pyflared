import asyncio
import atexit
import os
import pathlib
import re
import stat
from contextlib import ExitStack
from functools import cache, cached_property
from importlib.resources import files, as_file
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Iterator

from loguru import logger

from pyflared.api.tunnel_manager import TunnelManager
from pyflared.binary.binary_decorator import BinaryApp
from pyflared.shared.types import Mappings, Chunk, ChunkSignal, OutputChannel

__all__ = ["run_token_tunnel", "run_quick_tunnel", "version"]


@cached_property
def _bin_dir():
    # Bin directory lives inside the installed package
    return Path(__file__).resolve().parent / "bin"
    # return files('myapp.templates')


_binary_filename = "cloudflared" + ".exe" if os.name == "nt" else ""


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
    binary_ref = root / 'bin' / _binary_filename

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


token_tunnel_cmd = "tunnel", "run", "--token"
quick_tunnel_cmd = "tunnel", "--no-autoupdate", "--url"

cloudflared = BinaryApp(get_path())


@cloudflared.instant()
def version(): return "version"


quickflare_url_pattern: re.Pattern[bytes] = re.compile(rb'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)')
quickflare_url_pattern3: re.Pattern[bytes] = re.compile(rb'(Starting tunnel tunnelID=0733b006-8a87-4be8-8618-91c1e1fb429f)')


async def log_line(b: bytes):
    pass


async def filter_trycloudflare_url(stream_reader: asyncio.StreamReader, output_channel: OutputChannel) -> Chunk:
    line_data = await stream_reader.readline()
    logger.opt(raw=True).debug(line_data.decode())
    await log_line(line_data)
    if match := quickflare_url_pattern.search(line_data):
        return match.group(1)
    return ChunkSignal.SKIP


@cloudflared.daemon(stream_chunker=filter_trycloudflare_url)
async def run_quick_tunnel(service: str):
    return *quick_tunnel_cmd, service


@cloudflared.daemon()
def run_token_tunnel(token: str):
    return *token_tunnel_cmd, token


def confirm_token() -> bool:
    return True


async def log_all(stream_reader: asyncio.StreamReader, output_channel: OutputChannel) -> Chunk:
    line_data = await stream_reader.readline()
    logger.opt(raw=True).debug(line_data.decode())
    await log_line(line_data)
    return ChunkSignal.SKIP

x = "Registered tunnel connection connIndex="
@cloudflared.daemon(stream_chunker=log_all)
async def run_dns_fixed_tunnel(
        mappings: Mappings, api_token: str | None = None,
        remove_orphan: bool = True, tunnel_name: str | None = None):
    tunnel_manager = TunnelManager(api_token)
    if remove_orphan:
        await tunnel_manager.remove_orphans()
    tunnel_token = await tunnel_manager.fixed_dns_tunnel(mappings, tunnel_name=tunnel_name)
    return *token_tunnel_cmd, tunnel_token.get_secret_value()
