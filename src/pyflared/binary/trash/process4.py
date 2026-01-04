import asyncio
import logging
import os
import re
from abc import ABC
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, auto
from typing import Callable, Awaitable, Self

from pydantic import BaseModel

from pyflared.types import ProcessArgs

logger = logging.getLogger(__name__)





@dataclass(frozen=True)
class ProcessOut:
    chunk: bytes
    out_type: OutputChannel


# @dataclass(frozen=True)
# class ProcessOut:
#     chunk: bytes

# @dataclass(frozen=True)
# class StdOut(ProcessOut):
#     pass
#
#
# @dataclass(frozen=True)
# class StdErr(ProcessOut):
#     pass


class LogLevel(StrEnum):
    INFO = auto()
    ERROR = auto()
    DEBUG = auto()


@dataclass(frozen=True)
class LogEvent:
    level: LogLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


# @dataclass(frozen=True)
# class ProcessEvent(ABC):
#     line: str  # Move to bytes in the future if needed
#     timestamp: datetime = field(default_factory=datetime.now)
#
#     def __repr__(self) -> str:
#         # Format timestamp to HH:MM:SS (add .%f if you need milliseconds)
#         ts_str = self.timestamp.strftime("%H:%M:%S")
#
#         # Get the class name dynamically (StdOut or StdErr)
#         tag = self.__class__.__name__
#
#         # Strip trailing newlines from the line so it prints cleanly
#         clean_line = self.line.rstrip()
#
#         return f"[{ts_str}] [{tag}] {clean_line}"
#
#     def log(self):
#         match self:
#             case StdOut():
#                 logger.debug(self)
#             case StdErr():
#                 logger.warning(self)
#             case _:
#                 logger.info(self)

# @dataclass(frozen=True)
# class StdOut(ProcessEvent): pass
#
#
# @dataclass(frozen=True)
# class StdErr(ProcessEvent): pass


class ProcessOutPipe(AsyncIterator[bytes]):
    def __init__(self, queue: asyncio.Queue[bytes | None]):
        self.queue = queue

    async def __anext__(self) -> bytes:
        # Trust the Monitor/Context Manager to send None when done.
        if event := await self.queue.get():
            return event
        raise StopAsyncIteration


LineProcessor = Callable[[bytes, type[StdOut | StdErr]], StdOut | StdErr]
AsyncCmd = Callable[[], Awaitable[tuple[str, ...]]]


def default_line_processor(chunk: bytes, event_type: type[StdOut | StdErr]) -> StdOut | StdErr | None:
    if event := chunk.decode().strip():
        return event_type(event)
    else:
        return None


def default_async_cmd(cmd: ProcessArgs) -> AsyncCmd:
    if not cmd:
        raise ValueError("No command provided")

    async def _inner() -> ProcessArgs:
        return cmd

    return _inner


@dataclass()
class ProcessData:
    # binary_path = binary
    # async_cmd: AsyncCmd = async_cmd
    # def __init__(self, binary: str | os.PathLike, async_cmd: AsyncCmd, ):

    binary_path: str | os.PathLike
    async_cmd: AsyncCmd
    line_processor: LineProcessor = default_line_processor

    def run(self):
        return ProcessContext(self)

    @classmethod
    def from_binary_and_cmd(cls, binary: str | os.PathLike, cmd: ProcessArgs):
        return cls(binary, default_async_cmd(cmd))

    @classmethod
    def from_args(cls, args: ProcessArgs):
        return cls.from_binary_and_cmd(args[0], args[1:])


# pd = ProcessData.from_args("", "version")

# pd2 = pd.


Response = Callable[[ProcessOut], str | bytes | None]


class ProcessContext(AbstractAsyncContextManager[ProcessOutPipe]):
    def __init__(self, process_data: ProcessData):
        self.process_data = process_data

        self._process: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        # We define queue here, but typically it's cleaner to init in __aenter__
        # to ensure a fresh queue for every run if you ever relaxed the single-use rule.
        self._queue: asyncio.Queue[ProcessOut | None] = asyncio.Queue()

    @property
    def return_code(self) -> int | None:
        return self._process.returncode

    @property
    def is_running(self) -> bool:
        return self._process and self._process.returncode is None

    async def wait_for_completion(self):
        return await self._process.wait()

    async def _stream_pass(self, stream: asyncio.StreamReader, out_type: OutputChannel):
        try:
            while data_chunk := await self.read_chunk(stream):
                po = ProcessOut(data_chunk, out_type)
                self._queue.put_nowait(po)
        except Exception as e:
            # Only log if it's not a cancellation error
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"[{self.process_data.binary_path}] Reader failed: {e}")
            else:
                logger.debug(f"Reader closed: {e}")

    @classmethod
    async def read_chunk(cls, reader: asyncio.StreamReader) -> bytes:
        """Defaults to readline. Override for custom behavior."""
        return await reader.readline()

    @classmethod
    def logging(cls, process_out: ProcessOut) -> LogEvent | None:
        """Only log StdErr. Override for custom behavior."""
        if process_out.out_type == OutputChannel.STDERR:
            return LogEvent(LogLevel.DEBUG, str(process_out))
        else:
            return None

    async def _finalize_completion(self, readers: list[asyncio.Task]):

        # 1. Wait for reader pipes to finish
        await asyncio.gather(*readers, return_exceptions=True)

        # 2. Update the exit code
        try:
            self._process.stdin.close()
            await asyncio.wait_for(self._process.wait(), timeout=1.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # 3. Release the user
        self._queue.put_nowait(None)

    async def __aenter__(self) -> ProcessOutPipe:
        if self._process is not None:
            raise RuntimeError("Context already entered, make a new one")

        args = await self.process_data.async_cmd()

        logger.debug(f"Starting: {self.process_data.binary_path} {args}")
        # 1. Start Process
        process = await asyncio.create_subprocess_exec(
            self.process_data.binary_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )
        self._process = process

        # 2. Start Readers
        reader_tasks: list[asyncio.Task] = []

        if stdout := process.stdout:
            reader_tasks.append(asyncio.create_task(
                self._stream_pass(stdout, OutputChannel.STDOUT)
            ))

        if stderr := process.stderr:
            reader_tasks.append(asyncio.create_task(
                self._stream_pass(stderr, OutputChannel.STDERR)
            ))

        # 3. Start Finalizer
        finalizer_task = asyncio.create_task(
            self._finalize_completion(reader_tasks)
        )

        self._tasks = reader_tasks + [finalizer_task]

        return ProcessOutPipe(self._queue)

    async def __aexit__(self, exc_type, exc, tb):
        logger.info("Stopping binary...")

        if self._process is None:
            return

        # 1. Terminate Process
        if self._process.returncode is None:
            try:
                self._process.stdin.close()
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()

        # 2. Cancel ALL Tasks (Monitor included)
        for task in self._tasks:
            task.cancel()

        # 3. Wait for cancellations to settle
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # 4. SAFETY NET: Inject None
        # We just killed the Monitor. If the Monitor didn't run yet,
        # the queue is missing the sentinel. We must add it manually.
        self._queue.put_nowait(None)

    async def start_background(self, response: Response | None) -> int | None:
        async with self as service:
            async for event in service:
                if response:
                    if x := response(event):
                        self._process.stdin.write(x)
                event.log()

        return self._process.returncode


# class User(BaseModel):
#     id: int
#     name: str
#
# user = User(id=1, name="Alice")
# # Pydantic has this built-in by default
# user2 = user.model_copy(update(name="A"))

quickflare_url_pattern = re.compile(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)')

# @dataclass()
# class VA:
#     name: str
#     id: int
#
#     def w(self):
#         print("a")
#         pass
#
#
# def r():
#     print("a")
#
#
# va = VA("", 3)
#
#
# class VA2(VA):
#     def w(self):
#         print("b")
#
# va2 = VA2("", 3)

# class WE:
#
#     def __init__(self, id1: int):
#         self.id1 = id1
#
#     @classmethod
#     def w(cls) -> Self:
#         return cls(1)
#
#
# we = WE.w()
