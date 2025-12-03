import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

from pyflared.binary.process import ProcessContext


@dataclass(frozen=True)
class TextResult:
    stdout: str
    stderr: str
    return_code: int


class BinaryWrapper:
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

    def execute_streaming_response_from_async(self, async_cmd: Callable[[], Awaitable[tuple[str, ...]]]):
        return ProcessContext(self.binary, async_cmd=async_cmd)
