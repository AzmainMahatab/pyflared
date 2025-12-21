import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable

from pyflared.binary.process import ProcessContext, StdOut, StdErr


@dataclass(frozen=True)
class TextResult:
    stdout: str
    stderr: str
    return_code: int


# class ProcessBridge(ABC):
#
#     @abstractmethod
#     async def cmd(self) -> tuple[str, ...]:
#         pass
#
#     def chunk_to_event(self, byte_chunk: bytes, event_type: type[StdOut | StdErr]) -> StdOut | StdErr | None:
#         if x := byte_chunk.decode().strip():
#             return event_type(x)
#         else:
#             return None
#
#     @staticmethod
#     def from_command(cmd: tuple[str, ...]) -> "ProcessBridge":
#         class _CmdBridge(ProcessBridge):
#             async def cmd(self) -> tuple[str, ...]:
#                 return cmd
#
#         return _CmdBridge()



class BinaryWrapper:

    def __init__(self, binary: str | os.PathLike, ):
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
