import asyncio
import logging
import os
from abc import ABC
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Awaitable


@dataclass(frozen=True)
class ProcessEvent(ABC):
    line: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        return self.line


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


class ProcessContext(AbstractAsyncContextManager[ProcessInstance]):
    def __init__(self, binary: str | os.PathLike, *args: str,
                 async_cmd: Callable[[], Awaitable[tuple[str, ...]]] | None = None):
        self.cmd = str(binary)
        self.args = args
        self.async_cmd = async_cmd

        self._process: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        # We define queue here, but typically it's cleaner to init in __aenter__
        # to ensure a fresh queue for every run if you ever relaxed the single-use rule.
        self._queue: asyncio.Queue[StdOut | StdErr | None] = asyncio.Queue()

    async def _stream_reader(self, stream: asyncio.StreamReader, event_type: type[StdOut | StdErr]):
        try:
            while line_bytes := await stream.readline():
                if line := line_bytes.decode().strip():
                    # Direct access to self._queue is fine since this object manages it
                    self._queue.put_nowait(event_type(line))
        except Exception as e:
            # Only log if it's not a cancellation error
            if not isinstance(e, asyncio.CancelledError):
                logging.error(f"[{self.cmd}] Reader failed: {e}")

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

        logging.info(f"Starting: {self.cmd} {self.args}")
        # 1. Start Process
        process = await asyncio.create_subprocess_exec(
            self.cmd, *self.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self._process = process

        # 2. Start Readers
        reader_tasks: list[asyncio.Task] = []

        if stdout := process.stdout:
            reader_tasks.append(asyncio.create_task(
                self._stream_reader(stdout, StdOut)
            ))

        if stderr := process.stderr:
            reader_tasks.append(asyncio.create_task(
                self._stream_reader(stderr, StdErr)
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
        logging.info("Stopping binary...")

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

    async def _start_background(self) -> int | None:
        async with self as service:
            async for event in service:
                print(event)  # Switch to logs
        return service.return_code

    def start_background(self) -> asyncio.Task[int | None]:
        return asyncio.create_task(self._start_background())
