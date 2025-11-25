import asyncio
import logging
from abc import ABC
from asyncio import Queue
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
import os
from typing import AsyncIterator

from pyflared.cloudflared import get_path


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

    def __init__(self, process: asyncio.subprocess.Process,
                 queue: Queue[StdOut | StdErr | None]):
        self._process = process
        self._queue = queue

    @property
    def return_code(self) -> int | None:
        return self._process.returncode

    @property
    def is_running(self) -> bool:
        return self._process.returncode is None

    async def __anext__(self):
        # The Monitor guarantees that 'None' will arrive when the process is done, so we don't need to check returncode here.
        if event := await self._queue.get():
            return event
        raise StopAsyncIteration


class _ServiceContext(AbstractAsyncContextManager[_Service]):

    def __init__(self, binary: str | os.PathLike, *args: str):
        self.cmd = str(binary)
        self.args = args

        # Active state is None until __aenter__ runs
        self._process: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        self._queue: asyncio.Queue[StdOut | StdErr | None] = asyncio.Queue()

    async def _stream_reader(self, stream: asyncio.StreamReader, event_type: type[StdOut | StdErr]):
        try:
            while line_bytes := await stream.readline():
                if (line := line_bytes.decode().strip()) and (queue := self._queue):
                    queue.put_nowait(event_type(line))
        except Exception as e:
            logging.error(f"[{self.cmd}] Reader failed: {e}")

    async def _monitor_completion(self, process: asyncio.subprocess.Process, *readers: asyncio.Task):
        # 1. Wait for logs to finish
        if readers:
            await asyncio.gather(*readers, return_exceptions=True)

        # 2. Update the exit code (The Library handles the check)
        try:
            # If process is already dead, this returns instantly.
            # If process is still closing, this waits max 1.0s.
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except (asyncio.TimeoutError, Exception):
            pass

            # 3. Release the user
        self._queue.put_nowait(None)

    async def __aenter__(self) -> _Service:
        if self._process is not None:
            raise RuntimeError("Context already entered, make a new one")

        logging.info(f"Starting: {self.cmd} {self.args}")

        # 2. Start Process
        process = await asyncio.create_subprocess_exec(
            self.cmd, *self.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self._process = process
        reader_tasks: list[asyncio.Task] = []

        # 3. Start Pumps (Manual Task Management required here)
        if stdout := process.stdout:
            reader_tasks.append(
                asyncio.create_task(
                    self._stream_reader(stdout, StdOut)
                )
            )

        if stderr := process.stderr:
            reader_tasks.append(
                asyncio.create_task(
                    self._stream_reader(stderr, StdErr)
                )
            )

        monitor_task = asyncio.create_task(
            self._monitor_completion(process, *reader_tasks)
        )
        self._tasks = reader_tasks + [monitor_task]

        return _Service(process, self._queue)

    async def __aexit__(self, exc_type, exc, tb):
        logging.info("Stopping binary...")

        # Guard Clause: If start failed, nothing to clean
        if self._process is None:
            return

        proc = self._process

        # 2. Terminate Process
        if proc.returncode is None:
            try:
                proc.terminate()
                # Let it exit gracefully
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't exit gracefully'
                proc.kill()

        # Cancel  Monitor and Readers Tasks
        for t in self._tasks:
            t.cancel()

        # Wait for cancellations to settle
        await asyncio.gather(*self._tasks, return_exceptions=True)


class CloudflareTunnelService(_ServiceContext):
    def __init__(self, config: str):
        super().__init__(get_path(), "tunnel", "--config", config, "run")
