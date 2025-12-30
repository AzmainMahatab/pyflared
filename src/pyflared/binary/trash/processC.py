import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import final

from pyflared.binary.trash.process4 import OutputChannel
from pyflared.cloudflared import get_path

ArgType = str | bytes | os.PathLike[str] | os.PathLike[bytes]

logger = logging.getLogger(__name__)



InteractionResponse = Callable[[bytes, OutputChannel], str | bytes | None]


class ProcessMaster(ABC):
    @property
    @abstractmethod
    def binary(self) -> ArgType:
        pass

    @classmethod
    async def read_chunk(cls, stream: asyncio.StreamReader, out_type: OutputChannel) -> bytes | None:
        """Defaults to readline. Override for custom behavior, None indicates EOF."""
        return await stream.readline()

    async def _response_loop(
            self, process: asyncio.subprocess.Process,
            out_type: OutputChannel,
            interaction_handler: InteractionResponse | None):

        reader = process.stdout if out_type == OutputChannel.STDOUT else process.stderr

        while True:
            if chunk := await self.read_chunk(reader, out_type):
                if interaction_handler:
                    if res := interaction_handler(chunk, out_type):
                        process.stdin.write(res)
            else:  # End of stream
                break

    @final
    async def run(self, args: tuple[ArgType, ...],
                  initial_write: str | bytes | None = None,
                  response: InteractionResponse | None = None
                  ):

        process = await asyncio.create_subprocess_exec(
            self.binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        if initial_write:
            process.stdin.write(initial_write)

        await asyncio.gather(
            self._response_loop(process, OutputChannel.STDOUT, response),
            self._response_loop(process, OutputChannel.STDERR, response),
        )

        process.stdin.close()
        return await process.wait()


class ProcessInstance:
    def __init__(self, process: asyncio.subprocess.Process):
        self._process = process


# async def x():
#     return 1

# def process_maker() -> Coroutine[ProcessEvent, ArgType, int]:
#     process = await asyncio.create_subprocess_exec(
#         self.binary, *args,
#         stdout=asyncio.subprocess.PIPE,
#         stderr=asyncio.subprocess.PIPE,
#         stdin=asyncio.subprocess.PIPE
#     )


class CFProcess(ProcessMaster):
    binary = get_path()


class CF1:
    def quick_tunnel_cmd(self, service: str) -> tuple[ArgType, ...]:
