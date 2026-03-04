import asyncio
from collections.abc import Iterable
from dataclasses import dataclass

from pyflared.shared.types import AwaitableMaybe, OutputChannel, Responder
from pyflared.utils.asyncio.wait import safe_awaiter


@dataclass
class ProcessWriter:
    process: asyncio.subprocess.Process

    async def write(self, data: AwaitableMaybe[str | bytes]) -> None:
        """write to stdin."""
        if not self.process.stdin:
            return

        try:
            data = await safe_awaiter(data)
            if isinstance(data, str):
                data = data.encode()
            self.process.stdin.write(data)
            await self.process.stdin.drain()
        except BrokenPipeError:
            pass

    async def write_line(self, data: AwaitableMaybe[str]):
        line = await safe_awaiter(data) + "\n"
        await self.write(line)

    async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
        for responder in responders:
            response = await safe_awaiter(responder(chunk, channel))
            if response is not None:
                await self.write(response)
