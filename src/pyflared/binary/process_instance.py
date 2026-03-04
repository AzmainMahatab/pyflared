import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Callable
from dataclasses import dataclass
from typing import override, Self

from pyflared.binary.reader import combined_output
from pyflared.binary.writer import ProcessWriter
from pyflared.shared.types import ProcessOutput, StreamChunker, Responder, OutputChannel, AwaitableMaybe

type Mutator = Callable[[ProcessOutput], AwaitableMaybe[bytes]]


@dataclass
class ProcessInstance(ProcessWriter, AsyncIterable[ProcessOutput]):
    fixed_input: str | None
    chunker: StreamChunker | None = None
    responders: list[Responder] | None = None

    @override
    def __aiter__(self) -> AsyncIterator[ProcessOutput]:
        return combined_output(self, self.fixed_input, self.chunker, self.responders)

    async def stdout_only(self) -> AsyncIterator[bytes]:
        """Yields only stdout, but drains stderr."""
        async for output in self:
            if output.channel == OutputChannel.STDOUT:
                yield output.data

    async def stderr_only(self) -> AsyncIterator[bytes]:
        """Yields only stderr, but drains stdout."""
        async for output in self:
            if output.channel == OutputChannel.STDERR:
                yield output.data

    async def pipe_to(self, target: Self, mutator: Mutator | None = None) -> None:
        """Pipes the output of this process to another process."""
        async for output in self:
            if mutator:
                await target.write(mutator(output))
            elif output.channel == OutputChannel.STDOUT:
                await target.write(output.data)

    async def drain_wait(self) -> int:
        """Drains all output and waits until the process completes."""
        async for _ in self:
            pass
        return await self.process.wait()

    async def wait(self) -> int:
        """Waits until the process completes."""
        return await self.process.wait()

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    async def stop_gracefully(self):
        if self.process and self.process.returncode is None:
            if self.process.stdin:
                self.process.stdin.close()

            try:
                self.process.terminate()
                _ = await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except ProcessLookupError:
                # Process already dead
                pass
            except TimeoutError:
                self.process.kill()
                _ = await self.process.wait()
