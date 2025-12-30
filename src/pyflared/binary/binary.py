import asyncio
import os
from dataclasses import dataclass

from pyflared.binary.process import ProcessContext, ProcessData, AsyncCmd, LineProcessor, default_line_processor
from pyflared.typealias import ProcessArgs


@dataclass(frozen=True)
class TextResult:
    stdout: str
    stderr: str
    return_code: int


class BinaryWrapper:

    def __init__(self, binary: str | os.PathLike[str]):
        self.binary = binary

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

    # @classmethod
    # def execute_streaming_response_from_data(cls, data: ProcessData):
    #     return ProcessContext(data)

    def execute_streaming_response(self, *args: str):
        process_data = ProcessData.from_binary_and_cmd(self.binary, args)
        return ProcessContext(process_data)

    def execute_streaming_response_from_async(self, async_cmd: AsyncCmd):
        process_data = ProcessData(self.binary, async_cmd)
        return ProcessContext(process_data)


class B2:
    def __init__(self, binary: str | os.PathLike[str]):
        self.binary = binary
        line_processor: LineProcessor = default_line_processor

    # def execute(self, args: ProcessArgs):
