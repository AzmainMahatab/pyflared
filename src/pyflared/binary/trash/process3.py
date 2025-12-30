import asyncio
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from io import DEFAULT_BUFFER_SIZE
from typing import Callable, Awaitable, Self

from pydantic import BaseModel

from pyflared.typealias import ProcessArgs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessEvent(ABC):
    line: str  # Move to bytes in the future if needed
    timestamp: datetime = field(default_factory=datetime.now)

    def __repr__(self) -> str:
        # Format timestamp to HH:MM:SS (add .%f if you need milliseconds)
        ts_str = self.timestamp.strftime("%H:%M:%S")

        # Get the class name dynamically (StdOut or StdErr)
        tag = self.__class__.__name__

        # Strip trailing newlines from the line so it prints cleanly
        clean_line = self.line.rstrip()

        return f"[{ts_str}] [{tag}] {clean_line}"

    def log(self):
        match self:
            case StdOut():
                logger.debug(self)
            case StdErr():
                logger.warning(self)
            case _:
                logger.info(self)


@dataclass(frozen=True)
class StdOut(ProcessEvent): pass


@dataclass(frozen=True)
class StdErr(ProcessEvent): pass


AsyncCmd = Callable[[], Awaitable[tuple[str, ...]]]

LineProcessor = Callable[[bytes, type[StdOut | StdErr]], StdOut | StdErr]


class StreamProcessor[T](ABC):

    @classmethod
    async def read_chunk(cls, stream: asyncio.StreamReader) -> bytes:
        return await stream.read(DEFAULT_BUFFER_SIZE)

    @classmethod
    @abstractmethod
    async def process_chunk(cls, chunk: bytes) -> T:
        pass


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

class ProcessInstance(AsyncIterator[StdOut | StdErr]):
    queue: asyncio.Queue[StdOut | StdErr | None] = asyncio.Queue()

    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process

    @property
    def return_code(self) -> int | None:
        return self.process.returncode

    @property
    def is_running(self) -> bool:
        return self.process.returncode is None

    async def process_finish(self):
        await self.process.wait()

    async def _stream_pass(self, stream: asyncio.StreamReader, event_type: type[StdOut | StdErr]):
        try:
            while line_bytes := await stream.readline():
                if event := self.process_data.line_processor(line_bytes, event_type):
                    self._queue.put_nowait(event)
        except Exception as e:
            # Only log if it's not a cancellation error
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"[{self.process_data.binary_path}] Reader failed: {e}")
            else:
                logger.debug(f"Reader closed: {e}")

    async def __anext__(self) -> StdOut | StdErr:
        # Trust the Monitor/Context Manager to send None when done.
        if event := await self.queue.get():
            return event
        raise StopAsyncIteration

    async def wait_finish(self):
        # wait for readers to finish
        await asyncio.gather(*self.reader_tasks, return_exceptions=True)

        try:
            await asyncio.wait_for(self.process.wait(), timeout=1.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # Signal listener to stop
        self.queue.put_nowait(None)


# class StreamReader:
#     def __init__(self, stream: asyncio.StreamReader):
#         self.stream = stream
#
#     async def read_chunk(self) -> bytes:
#         return await self.stream.readline()


class ProcessContext(AbstractAsyncContextManager[ProcessInstance]):
    stdout_sp: StreamProcessor[ProcessEvent] = StreamProcessor()
    stderr_sp: StreamProcessor[ProcessEvent] = StreamProcessor()

    def __init__(self, process_data: ProcessData):
        self.process_data = process_data

        self.process_instance: ProcessInstance | None = None

        # self._process: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        # We define queue here, but typically it's cleaner to init in __aenter__
        # to ensure a fresh queue for every run if you ever relaxed the single-use rule.

    async def stdout_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        return await stream.readline()

    async def stderr_read_chunk(self, stream: asyncio.StreamReader) -> bytes:
        return await stream.readline()

    async def process_stream(self, sp: StreamProcessor[ProcessEvent], stream: asyncio.StreamReader):
        pass

    async def _stream_pass(self, stream: asyncio.StreamReader, event_type: type[StdOut | StdErr]):
        try:
            while line_bytes := await stream.readline():
                if event := self.process_data.line_processor(line_bytes, event_type):
                    self._queue.put_nowait(event)
        except Exception as e:
            # Only log if it's not a cancellation error
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"[{self.process_data.binary_path}] Reader failed: {e}")
            else:
                logger.debug(f"Reader closed: {e}")

    async def _monitor_completion(self, process: asyncio.subprocess.Process, readers: list[asyncio.Task]):
        # 1. Wait for logs to finish
        if readers:
            await asyncio.gather(*readers, return_exceptions=True)

        # 2. Update the exit code
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except (asyncio.TimeoutError, Exception):
            pass

        # 3. Release the user
        self._queue.put_nowait(None)

    async def __aenter__(self) -> ProcessInstance:
        if self._process is not None:
            raise RuntimeError("Context already entered, make a new one")

        args = await self.process_data.async_cmd()

        logger.debug(f"Starting: {self.process_data.binary_path} {args}")
        # 1. Start Process
        process = await asyncio.create_subprocess_exec(
            self.process_data.binary_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # self._process = process

        # 2. Start Readers
        reader_tasks: list[asyncio.Task] = []

        if stdout := process.stdout:
            reader_tasks.append(asyncio.create_task(
                self._stream_pass(stdout, StdOut)
            ))

        if stderr := process.stderr:
            reader_tasks.append(asyncio.create_task(
                self._stream_pass(stderr, StdErr)
            ))

        # 3. Start Monitor
        # Note: Pass the LIST of readers, don't unpack with *.
        # Easier to handle inside the monitor logic.
        monitor_task = asyncio.create_task(
            self._monitor_completion(process, reader_tasks)
        )

        self._tasks = reader_tasks + [monitor_task]
        p = ProcessInstance(process)
        self.process_instance = p
        return p

    async def __aexit__(self, exc_type, exc, tb):
        logger.info("Stopping binary...")

        if self.process_instance is None:
            return

        # 1. Terminate Process
        if self._process.returncode is None:
            try:
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

    async def start_background(self) -> int | None:
        async with self as service:
            async for event in service:
                event.log()
        return service.return_code


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
