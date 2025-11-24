import asyncio
from asyncio import Queue
from contextlib import AbstractAsyncContextManager
from os import PathLike
from typing import AsyncIterator, Optional

from pyflared.cloudflared import get_path
from pyflared.qe.asw import ProcessEvent, StdOut, StdErr


# --- CLASS 1: The Active Iterator (Private-ish) ---
# This class ONLY exists while the process is running.
# The user cannot create this manually; the Service gives it to them.

class _RunningBinary(AsyncIterator[ProcessEvent]):
    def __init__(
            self,
            process: asyncio.subprocess.Process,
            queue: asyncio.Queue,
            tasks: list[asyncio.Task]
    ):
        self._process = process
        self._queue = queue
        self._tasks = tasks

    async def __anext__(self) -> ProcessEvent:
        # Check if process died and queue is empty
        if self._process.returncode is not None and self._queue.empty():
            raise StopAsyncIteration

        if event := await self._queue.get():
            return event

        raise StopAsyncIteration


# --- CLASS 2: The Service Configuration (Public) ---
# This class is NOT an Iterator. It is ONLY a Context Manager.

class BinaryService(AbstractAsyncContextManager["_RunningBinary"]):
    def __init__(self, binary: str | PathLike, *args: str):
        self.cmd = str(binary)
        self.args = args

        # 1. Initialize State as None (Kotlin: null)
        # This defines the object structure immediately.
        self._active_process: Optional[asyncio.subprocess.Process] = None
        self._active_tasks: list[asyncio.Task] = []
        self._active_queue: Optional[asyncio.Queue] = None

    async def _stream_reader(self, stream, queue, event_type):
        # ... (Same as before) ...
        pass

    async def __aenter__(self) -> _RunningBinary:
        # 2. Local variables for setup
        queue: asyncio.Queue[Optional[ProcessEvent]] = asyncio.Queue()
        tasks: list[asyncio.Task] = []

        # 3. Start Process
        process = await asyncio.create_subprocess_exec(
            self.cmd, *self.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 4. Start Tasks
        if stdout := process.stdout:
            tasks.append(asyncio.create_task(
                self._stream_reader(stdout, queue, StdOut)
            ))
        if stderr := process.stderr:
            tasks.append(asyncio.create_task(
                self._stream_reader(stderr, queue, StdErr)
            ))

        # 5. Assign to State (Now it is no longer None)
        self._active_process = process
        self._active_tasks = tasks
        self._active_queue = queue

        return _RunningBinary(process, queue, tasks)

    async def __aexit__(self, exc_type, exc, tb):
        # 6. Standard Null Check (No more hack!)
        if self._active_process is None:
            # __aenter__ crashed before starting process (e.g. binary not found)
            # Nothing to clean up.
            return

        # Safe to access these now because _active_process is not None
        proc = self._active_process
        tasks = self._active_tasks
        queue = self._active_queue

        # --- Cleanup Logic ---
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

        for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        if queue:
            queue.put_nowait(None)

        # Optional: Reset state to None so the service object could theoretically be reused
        self._active_process = None


class Cloudflared(BinaryService):
    """
    Specialized wrapper for the cloudflared binary.
    """

    def __init__(self, *args: str):
        super().__init__(get_path(), *args)
