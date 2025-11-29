import asyncio
import os
import sys
from dataclasses import dataclass

from pyflared.cloudflared import get_path
from pyflared.f1.C import ProcessContext

__all__ = ["cloudflared_binary", "run_token_tunnel", "run_quick_tunnel", "version"]

from pyflared.tunnel import Mapping, TunnelManager


@dataclass(frozen=True)
class TextResult:
    stdout: str
    stderr: str
    return_code: int


class _BinaryWrapper:
    def __init__(self, binary: str | os.PathLike):
        self.binary = str(binary)

    async def execute_await_response(self, *args: str):
        proc = await asyncio.create_subprocess_exec(
            self.binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 2. Wait for it to finish and grab all output at once
        # communicate() handles the memory buffer reading for you.
        stdout_bytes, stderr_bytes = await proc.communicate()

        # 3. Return clean results
        return TextResult(
            stdout_bytes.decode().strip(),
            stderr_bytes.decode().strip(),
            proc.returncode or 0,
        )

    def execute_streaming_response(self, *args: str):
        return ProcessContext(self.binary, *args)


# class CloudflareBinary(_BinaryWrapper):
#     def __init__(self):
#         super().__init__(get_path())
# def tunnel(token: str):
#     return _ServiceContext(get_path(), "tunnel", "run", "--token", token)
#


cloudflared_binary = _BinaryWrapper(get_path())

token_tunnel_cmd = "tunnel", "run", "--token"
quick_tunnel_cmd = "tunnel", "--no-autoupdate", "--url"


def run_token_tunnel(token: str) -> ProcessContext:
    return cloudflared_binary.execute_streaming_response(*token_tunnel_cmd, token)


def run_quick_tunnel(service: str):
    return cloudflared_binary.execute_streaming_response(*quick_tunnel_cmd, service)


async def run_dns_fixed_tunnel(api_token: str, *mappings: Mapping):
    tunnel_manager = TunnelManager(api_token)
    tunnel_manager.remove_orphans()
    token = tunnel_manager.tunnel2(*mappings)
    return run_token_tunnel(token)


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
