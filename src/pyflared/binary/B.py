import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from io import DEFAULT_BUFFER_SIZE


class Process(ABC):
    # stream: asyncio.StreamReader
    binary: str | bytes | os.PathLike[str] | os.PathLike[bytes]
    args: str | bytes | os.PathLike[str] | os.PathLike[bytes]

    # Why 2 methods? Because user can override stdout and stderr differently
    # @abstractmethod
    async def stdout_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        return await stream.read(DEFAULT_BUFFER_SIZE)

    async def stderr_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        return await stream.read(DEFAULT_BUFFER_SIZE)

    # def each_read(self, byte_chunk: bytes):
    #     pass

    @abstractmethod
    def on_each_stdout(self, byte_chunk: bytes):
        pass

    def on_each_stderr(self, byte_chunk: bytes):
        pass

    # @abstractmethod
    def stdout_response(self, byte_chunk: bytes) -> str | bytes | None:
        return None

    # @abstractmethod
    def stderr_response(self, byte_chunk: bytes) -> str | bytes | None:
        return None

    # @abstractmethod
    def blind_write(self) -> str | bytes | None:
        return None

    async def _response_loop(self, reader: asyncio.streams.StreamReader,
                             writer: asyncio.streams.StreamWriter,
                             read_chunk: Callable[[asyncio.StreamReader], Awaitable[bytes]],
                             on_chunk: Callable[[bytes], None],
                             response: Callable[[bytes], str | bytes | None]):
        while True:
            if chunk := await read_chunk(reader):
                on_chunk(chunk)
                if res := response(chunk):
                    writer.write(res)
            else:  # End of stream
                break

    # async def _response_loop(self, sr: asyncio.streams.StreamReader):
    #     while True:
    #         if stdout_chunk := await self.stdout_read_chunk(sr):
    #             self.each_stdout(stdout_chunk)
    #             self.stdout_response(stdout_chunk)
    #         else:  # End of stream
    #             break

    async def _stdout_loop(self, sr: asyncio.streams.StreamReader, sw: asyncio.streams.StreamWriter):
        await self._response_loop(sr, sw, self.stdout_read_chunk, self.on_each_stdout, self.stdout_response)

    async def _stderr_loop(self, sr: asyncio.streams.StreamReader, sw: asyncio.streams.StreamWriter):
        await self._response_loop(sr, sw, self.stderr_read_chunk, self.on_each_stderr, self.stderr_response)

    async def run(self):
        process = await asyncio.create_subprocess_exec(
            self.binary, self.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        if initial_write := self.blind_write():
            process.stdin.write(initial_write)

        await asyncio.gather(
            self._stdout_loop(process.stdout, process.stdin),
            self._stderr_loop(process.stderr, process.stdin),
        )
        process.stdin.close()
        return await process.wait()
