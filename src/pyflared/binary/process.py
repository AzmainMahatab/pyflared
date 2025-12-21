import asyncio
import logging
import os
import re
from abc import ABC
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Awaitable, Self

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessEvent(ABC):
    line: str  # Move to bytes in future if needed
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        # Format timestamp to HH:MM:SS (add .%f if you need milliseconds)
        ts_str = self.timestamp.strftime("%H:%M:%S")

        # Get the class name dynamically (StdOut or StdErr)
        tag = self.__class__.__name__

        # Strip trailing newlines from the line so it prints cleanly
        clean_line = self.line.rstrip()

        return f"[{ts_str}] [{tag}] {clean_line}"


@dataclass(frozen=True)
class StdOut(ProcessEvent): pass


@dataclass(frozen=True)
class StdErr(ProcessEvent): pass


class ProcessInstance(AsyncIterator[StdOut | StdErr]):
    def __init__(self, process: asyncio.subprocess.Process, queue: asyncio.Queue):
        self._process = process
        self._queue = queue

    @property
    def return_code(self) -> int | None:
        return self._process.returncode

    @property
    def is_running(self) -> bool:
        return self._process.returncode is None

    async def __anext__(self) -> StdOut | StdErr:
        # Trust the Monitor/Context Manager to send None when done.
        if event := await self._queue.get():
            return event
        raise StopAsyncIteration


LineProcessor = Callable[[bytes, type[StdOut | StdErr]], StdOut | StdErr]
AsyncCmd = Callable[[], Awaitable[tuple[str, ...]]]


def default_line_processor(chunk: bytes, event_type: type[StdOut | StdErr]) -> StdOut | StdErr | None:
    if event := chunk.decode().strip():
        return event_type(event)
    else:
        return None


@dataclass()
class ProcessData:
    # binary_path = binary
    # async_cmd: AsyncCmd = async_cmd
    # def __init__(self, binary: str | os.PathLike, async_cmd: AsyncCmd, ):

    binary_path: str | os.PathLike
    async_cmd: AsyncCmd
    line_processor: LineProcessor = default_line_processor


class ProcessContext(AbstractAsyncContextManager[ProcessInstance]):
    def __init__(self, binary: str | os.PathLike, *args: str,
                 async_cmd: AsyncCmd | None = None,
                 line_processor: LineProcessor = default_line_processor):

        self.binary_path = binary
        self.args = args

        self.async_cmd = async_cmd

        self.line_processor = line_processor

        self._process: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        # We define queue here, but typically it's cleaner to init in __aenter__
        # to ensure a fresh queue for every run if you ever relaxed the single-use rule.
        self._queue: asyncio.Queue[StdOut | StdErr | None] = asyncio.Queue()

    async def _stream_pass(self, stream: asyncio.StreamReader, event_type: type[StdOut | StdErr]):
        try:
            while line_bytes := await stream.readline():
                if event := self.line_processor(line_bytes, event_type):
                    self._queue.put_nowait(event)
        except Exception as e:
            # Only log if it's not a cancellation error
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"[{self.binary_path}] Reader failed: {e}")
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

        if not self.args:
            if self.async_cmd:
                self.args = await self.async_cmd()
            else:
                raise RuntimeError("No args provided")

        logger.info(f"Starting: {self.binary_path} {self.args}")
        # 1. Start Process
        process = await asyncio.create_subprocess_exec(
            self.binary_path, *self.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self._process = process

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

        return ProcessInstance(process, self._queue)

    async def __aexit__(self, exc_type, exc, tb):
        logger.info("Stopping binary...")

        if self._process is None:
            return

        # 1. Terminate Process
        if self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()

        # 2. Cancel ALL Tasks (Monitor included)
        for t in self._tasks:
            t.cancel()

        # 3. Wait for cancellations to settle
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # 4. SAFETY NET: Inject None
        # We just killed the Monitor. If the Monitor didn't run yet,
        # the queue is missing the sentinel. We must add it manually.
        self._queue.put_nowait(None)

    async def start_background(self) -> int | None:
        async with self as service:
            async for event in service:
                # logger.debug()
                print(event)  # TODO: Switch to logs
        return service.return_code


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

class WE:

    def __init__(self, id1: int):
        self.id1 = id1

    @classmethod
    def w(cls) -> Self:
        return cls(1)


we = WE.w()