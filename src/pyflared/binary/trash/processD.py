import asyncio
import logging
import os
from contextlib import asynccontextmanager

from pyflared.cloudflared import get_path

ArgType = str | bytes | os.PathLike[str] | os.PathLike[bytes]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def open_tunnel(binary: ArgType, args: tuple[ArgType, ...]):
    # ... setup, triggers, logging ...
    process = await asyncio.create_subprocess_exec(binary, *args)
    try:
        yield process
    finally:
        # Standard Cleanup
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                process.kill()
                await process.wait()
        await wrapper.stop()


# ... cleanup ...

class CFProcess(ProcessMaster):
    binary = get_path()


class CF1:
    def quick_tunnel_cmd(self, service: str) -> tuple[ArgType, ...]:
