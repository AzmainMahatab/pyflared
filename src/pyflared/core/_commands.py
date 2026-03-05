import asyncio
import atexit
import pathlib
import re
import stat
from collections.abc import Iterator
from contextlib import ExitStack
from functools import cache
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path

from loguru import logger

from pyflared.shared._patterns import config_pattern, starting_tunnel, tunnel_connection_pattern
from pyflared.api_sdk.parse import Mapping
from pyflared.binary.binary_decorator import BinaryApp
from pyflared.shared.consts import IS_WINDOWS
from pyflared.core.tunnel_manager import TunnelManager
from pyflared.shared.contants import APP_NAME
from pyflared.shared.types import Chunk, ChunkSignal, OutputChannel

__all__ = ["binary_path",
           "binary_version",
           "run_dns_fixed_tunnel",
           "run_quick_tunnel",
           "run_token_tunnel",
           "cleanup"]


@cache
def _bin_dir():
    # Bin directory lives inside the installed package
    return Path(__file__).resolve().parent / "bin"


_binary_filename = f"cloudflared{".exe" if IS_WINDOWS else ""}"


def _ensure_posix_executable(path: pathlib.Path) -> None:
    if not IS_WINDOWS:
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
global_exit_stack = ExitStack()
_ = atexit.register(global_exit_stack.close)


@cache
def binary_path() -> pathlib.Path:
    # 1. Get package root
    root_pkg_name: str = __package__.split(".")[0] if __package__ else APP_NAME

    root = files(root_pkg_name)
    binary_ref = root / 'bin' / _binary_filename

    # 2. "Mount" the file
    # This guarantees 'path' is a real file system path (original or temp extracted).
    path = global_exit_stack.enter_context(as_file(binary_ref))

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

cloudflared = BinaryApp(binary_path)


@cloudflared.instant()
def binary_version(): return "version"


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


def confirm_token() -> bool:
    return True


async def log_all_n_skip(stream_reader: asyncio.StreamReader, _: OutputChannel) -> Chunk:
    line_data = await stream_reader.readline()
    logger.opt(raw=True).debug(line_data.decode())
    return ChunkSignal.SKIP


x = "Registered tunnel connection connIndex="

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
def run_token_tunnel(token: str):
    return *token_tunnel_cmd, token


@cloudflared.daemon(stream_chunker=fixed_tunnel_tracing)
async def run_dns_fixed_tunnel(mappings: list[Mapping], tunnel_name: str | None = None, force: bool = False, ):
    """Create a DNS-mapped Cloudflare Tunnel for the given domain-to-service mappings.

    Tunnel lifecycle is determined by the ``tunnel_name`` parameter:

    * **Unnamed (default):** The tunnel is treated as ephemeral. A new tunnel is
      created on every invocation and both the tunnel and its associated DNS
      records are automatically deleted on shutdown (e.g. Ctrl+C).
    * **Named:** The tunnel is treated as persistent. If a tunnel with the given
      name already exists it is reused; otherwise a new one is created. On
      shutdown the tunnel and DNS records are preserved so subsequent runs can
      reconnect instantly. Named tunnels also protect their DNS records from
      being overwritten by other tunnel setups — unless ``force`` is ``True``.

    Args:
        mappings: Domain-to-service pairs (e.g. ``api.example.com=localhost:8000``).
        tunnel_name: Optional human-readable name. ``None`` ⟹ ephemeral,
            any string ⟹ persistent.
        force: When ``True``, claim DNS records even if they are currently owned
            by another named (and potentially active) tunnel.
    """
    async with TunnelManager() as tm:
        running_tunnel = await tm.subdomain_mapped_tunnel(mappings, tunnel_name=tunnel_name, force=force)
        try:
            yield *token_tunnel_cmd, running_tunnel.tunnel_token.get_secret_value()
        finally:
            if not tunnel_name:
                await running_tunnel.clean_up()


async def cleanup(everything: bool = False, ):
    async with TunnelManager() as tm:
        await tm.cleanup(everything)
