import asyncio
import atexit
import os
import pathlib
import re
import stat
from collections.abc import Iterator
from contextlib import ExitStack
from functools import cache, cached_property
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path

from loguru import logger

from pyflared.api_sdk.tunnel_manager import TunnelManager
from pyflared.binary.binary_decorator import BinaryApp
from pyflared.shared.types import Chunk, ChunkSignal, Mappings, OutputChannel

__all__ = ["run_quick_tunnel", "run_token_tunnel", "version"]


@cached_property
def _bin_dir():
    # Bin directory lives inside the installed package
    return Path(__file__).resolve().parent / "bin"
    # return files('myapp.templates')


_binary_filename = f"cloudflared{".exe" if os.name == "nt" else ""}"


# + (".exe" if os.name == "nt" else "")


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


# noinspection PyAbstractClass
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


async def filter_trycloudflare_url(stream_reader: asyncio.StreamReader, _: OutputChannel) -> Chunk:
    line_data = await stream_reader.readline()
    logger.opt(raw=True).debug(line_data.decode())
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


async def log_all_n_skip(stream_reader: asyncio.StreamReader, _: OutputChannel) -> Chunk:
    line_data = await stream_reader.readline()
    logger.opt(raw=True).debug(line_data.decode())
    return ChunkSignal.SKIP


x = "Registered tunnel connection connIndex="

starting_tunnel = b"Starting tunnel tunnelID="
config_pattern = b"Updated to new configuration config="
tunnel_connection_pattern = b"connIndex="

patterns = (starting_tunnel, config_pattern, tunnel_connection_pattern)

# re.escape ensures special characters (like . or *) don't break the regex
combined_pattern = re.compile(b"|".join(re.escape(p) for p in patterns))


async def fixed_tunnel_tracing(stream_reader: asyncio.StreamReader, _: OutputChannel) -> Chunk:
    line_data = await stream_reader.readline()
    logger.opt(raw=True).debug(line_data.decode())
    if starting_tunnel in line_data or tunnel_connection_pattern in line_data or config_pattern in line_data:
        return line_data
    return ChunkSignal.SKIP


@cloudflared.daemon(stream_chunker=fixed_tunnel_tracing)
async def run_dns_fixed_tunnel(
        mappings: Mappings, api_token: str | None = None, *,
        remove_orphan: bool = True, tunnel_name: str | None = None):
    tunnel_manager = TunnelManager(api_token)
    if remove_orphan:
        await tunnel_manager.remove_orphans()
    tunnel_token = await tunnel_manager.fixed_dns_tunnel(mappings, tunnel_name=tunnel_name)
    return *token_tunnel_cmd, tunnel_token.get_secret_value()
