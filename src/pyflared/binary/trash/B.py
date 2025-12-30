import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from io import DEFAULT_BUFFER_SIZE
from typing import final, Coroutine

from pyflared.binary.process import ProcessEvent
from pyflared.cloudflared import get_path

ArgType = str | bytes | os.PathLike[str] | os.PathLike[bytes]

logger = logging.getLogger(__name__)


class Process(ABC):

    @property
    @abstractmethod
    def binary(self) -> ArgType:
        pass

    # Why 2 methods? Because user can override stdout and stderr differently
    # @abstractmethod
    async def stdout_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        return await stream.read(DEFAULT_BUFFER_SIZE)

    async def stderr_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        return await stream.read(DEFAULT_BUFFER_SIZE)

    # @abstractmethod
    def stdout_response(self, byte_chunk: bytes) -> str | bytes | None:
        return None

    # @abstractmethod
    def stderr_response(self, byte_chunk: bytes) -> str | bytes | None:
        return None

    # @abstractmethod
    @classmethod
    def init_write(cls) -> str | bytes | None:
        return None

    async def _response_loop(
            self, reader: asyncio.streams.StreamReader,
            writer: asyncio.streams.StreamWriter,
            read_chunk: Callable[[asyncio.StreamReader], Awaitable[bytes]],
            response: Callable[[bytes], str | bytes | None]):

        while True:
            if chunk := await read_chunk(reader):
                if res := response(chunk):
                    writer.write(res)
            else:  # End of stream
                break

    async def _stdout_loop(self, sr: asyncio.streams.StreamReader, sw: asyncio.streams.StreamWriter):
        await self._response_loop(sr, sw, self.stdout_read_chunk, self.stdout_response)

    async def _stderr_loop(self, sr: asyncio.streams.StreamReader, sw: asyncio.streams.StreamWriter):
        await self._response_loop(sr, sw, self.stderr_read_chunk, self.stderr_response)

    @final
    async def run(self, args: tuple[ArgType, ...]):
        process = await asyncio.create_subprocess_exec(
            self.binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        if initial_write := self.init_write():
            process.stdin.write(initial_write)

        await asyncio.gather(
            self._stdout_loop(process.stdout, process.stdin),
            self._stderr_loop(process.stderr, process.stdin),
        )

        process.stdin.close()
        return await process.wait()


# async def x():
#     return 1

# def process_maker() -> Coroutine[ProcessEvent, ArgType, int]:
#     process = await asyncio.create_subprocess_exec(
#         self.binary, *args,
#         stdout=asyncio.subprocess.PIPE,
#         stderr=asyncio.subprocess.PIPE,
#         stdin=asyncio.subprocess.PIPE
#     )


class CFProcess(Process):
    binary = get_path()

    async def stderr_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        x = await stream.readline()

        return x


class CF1:
    def quick_tunnel_cmd(self, service: str) -> tuple[ArgType, ...]:
