import asyncio
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ProcessHandle:
    """The object returned by the context manager."""
    process: asyncio.subprocess.Process

    @property
    def stdout(self) -> AsyncIterator[str]:
        """Expose raw stdout as an async iterator."""

        async def _iterate():
            if self.process.stdout:
                async for line in self.process.stdout:
                    yield line.decode().strip()

        return _iterate()

    @property
    def stderr(self) -> AsyncIterator[str]:
        """Expose raw stderr as an async iterator."""

        async def _iterate():
            if self.process.stderr:
                async for line in self.process.stderr:
                    yield line.decode().strip()

        return _iterate()

    async def stream_merged(self) -> AsyncIterator[tuple[str, str]]:
        """
        Helper to join streams.
        Yields tuple: ('STDOUT', line) or ('STDERR', line)
        """
        queue = asyncio.Queue()

        async def reader(source: AsyncIterator[str], label):
            async for line in source:
                await queue.put((label, line))

        # Start background tasks to feed the queue
        # In a real app, you'd manage these tasks so they cancel if the loop breaks
        async with asyncio.TaskGroup() as tg:
            tg.create_task(reader(self.stdout, 'STDOUT'))
            tg.create_task(reader(self.stderr, 'STDERR'))

            # This is a simplified consumer logic
            # In production, you need a way to break this loop when process ends
            while not queue.empty() or self.stdout.returncode is None:
                # while not queue.empty() or self.process.returncode is None:
                # Logic to wait for item or process exit would go here
                # This is just for API demonstration
                item = await queue.get()
                yield item


class MergedAsyncIterator(AsyncIterator[tuple[str, str]]):
    """An async iterator that merges stdout and stderr streams."""

    def __init__(self, std_out, std_err):
        self.queue = asyncio.Queue()
        self.tasks = []

    async def _reader(self, source: AsyncIterator[str], label: str):
        async for line in source:
            await self.queue.put((label, line))

    async def __anext__(self) -> tuple[str, str]:
        if self.handle.process.returncode is not None and self.queue.empty():
            for task in self.tasks:
                task.cancel()
            raise StopAsyncIteration
        return await self.queue.get()
