import asyncio
import logging
from abc import ABC
from asyncio import Queue
from asyncio.subprocess import Process
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from os import PathLike
from typing import AsyncIterator


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


class _Service(AsyncIterator[StdOut | StdErr]):

    def __init__(self, process: Process, queue: Queue[StdOut | StdErr | None]):
        self._process = process
        self._queue = queue

    @property
    def return_code(self) -> int | None:
        return self._process.returncode

    @property
    def is_running(self) -> bool:
        return self._process.returncode is None

    async def __anext__(self):
        # Check if process died + queue empty (Exited without writing anything)
        if not self.is_running and self._queue.empty():
            raise StopAsyncIteration

        if event := await self._queue.get():
            return event
        raise StopAsyncIteration


class _ServiceFactory(AbstractAsyncContextManager[_Service]):

    def __init__(self, binary: str | PathLike, *args: str):
        self.cmd = str(binary)
        self.args = args

        # Active state is None until __aenter__ runs
        self._active_process: asyncio.subprocess.Process | None = None
        self._active_tasks: list[asyncio.Task] = []
        self._active_queue: asyncio.Queue[StdOut | StdErr | None] | None = None

    async def _stream_reader(self, stream: asyncio.StreamReader,
                             queue: asyncio.Queue[StdOut | StdErr | None],
                             event_type: type[StdOut | StdErr]):
        try:
            while line_bytes := await stream.readline():
                if (line := line_bytes.decode().strip()) and (queue := self._active_queue):
                    queue.put_nowait(event_type(line))
        except Exception as e:
            logging.error(f"[{self.cmd}] Reader failed: {e}")

    async def __aenter__(self) -> _Service:
        if self._active_process is not None:
            raise RuntimeError("Service already ran.")

        logging.info(f"Starting: {self.cmd} {self.args}")

        # 1. Setup Run State
        queue: asyncio.Queue[StdOut | StdErr | None] = asyncio.Queue()
        tasks: list[asyncio.Task] = []

        # 2. Start Process
        process = await asyncio.create_subprocess_exec(
            self.cmd, *self.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self._active_process = process

        # 3. Start Pumps (Manual Task Management required here)
        if stdout := process.stdout:
            tasks.append(asyncio.create_task(
                self._stream_reader(stdout, queue, StdOut)
            ))
        if stderr := process.stderr:
            tasks.append(
                asyncio.create_task(self._stream_reader(stderr, queue, StdErr))
            )

        # 4. Store State
        self._active_queue = queue
        self._active_tasks = tasks

        return _Service(process, queue)

    async def __aexit__(self, exc_type, exc, tb):
        logging.info("Stopping binary...")

        # 1. Guard Clause: If start failed, nothing to clean
        if self._active_process is None:
            return

        proc = self._active_process

        # 2. Terminate Process
        if proc.returncode is None:
            try:
                proc.terminate()
                # Let it exit gracefully
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't exit gracefully'
                proc.kill()

        # 3. Cancel Tasks (Manual TaskGroup logic)
        for t in self._active_tasks:
            t.cancel()

        # Wait for cancellations to settle
        await asyncio.gather(*self._active_tasks, return_exceptions=True)

        # 4. Sentinel to unlock the iterator if it's waiting
        if self._active_queue:
            self._active_queue.put_nowait(None)

        # Reset state to allow re-use (optional)
        self._active_process = None
