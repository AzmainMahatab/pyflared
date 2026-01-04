import asyncio
import contextlib
import inspect
import logging
from dataclasses import dataclass, field
from typing import AsyncIterable, AsyncIterator, AsyncContextManager, Iterable, Callable

import aiostream
from beartype.door import die_if_unbearable

from pyflared.binary.context import Mutator
from pyflared.types import OutputChannel, StreamChunker, Responder, CmdArg, CmdArgs, Guard, \
    ProcessOutput, AwaitableMaybe, ChunkSignal, CommandError
from pyflared.utils.async_helper import safe_awaiter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunningProcess(AsyncIterable[ProcessOutput]):
    """
    A safe, active handle to a running process.
    """
    process: asyncio.subprocess.Process
    process_streams: AsyncIterator[ProcessOutput]

    def __aiter__(self) -> AsyncIterator[ProcessOutput]:
        return self.process_streams

    async def write(self, data: AwaitableMaybe[str | bytes]) -> None:
        """write to stdin."""
        if not self.process.stdin:
            return
        try:
            data = await safe_awaiter(data)
            self.process.stdin.write(data)
            if isinstance(data, str) and not data.endswith("\n"):
                self.process.stdin.write(b"\n")
            await self.process.stdin.drain()
        except BrokenPipeError:
            pass

    async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
        for responder in responders:
            response = responder(chunk, channel)
            if inspect.isawaitable(response):
                response = await response
            if response is not None:
                await self.write(response)

    async def pipe_to(self, target: RunningProcess, mutator: Mutator | None = None) -> None:
        async for output in self:
            if mutator:
                await target.write(mutator(output))
            elif output.channel == OutputChannel.STDOUT:
                await target.write(output.data)

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

    async def drain_wait(self) -> None:
        """Drains all output until the process completes."""
        async for _ in self:
            pass
        await self.process.wait()

    @property
    def returncode(self) -> int | None:
        return self.process.returncode


@dataclass
class ProcessExecutor(AsyncContextManager[RunningProcess]):
    """
    Manages the lifecycle of a subprocess and its associated IO streams.
    """
    binary_path: CmdArg
    cmd_args: CmdArgs

    # Configuration
    guards: list[Guard] | None = None
    fixed_input: str | None = None
    chunker: StreamChunker | None = None
    # out_filter: ProcessOutputFilter | None = None
    responders: list[Responder] | None = None

    # Internal State
    process: asyncio.subprocess.Process | None = None
    stack: contextlib.AsyncExitStack = field(default_factory=contextlib.AsyncExitStack, init=False)

    @classmethod
    async def _validate_guards(cls, guards: Iterable[Guard]):
        for guard in guards:
            result = guard()
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise CommandError(f"Precondition failed: {guard.__name__}")

    async def __aenter__(self) -> RunningProcess:
        # 1. Prepare Arguments
        args = await safe_awaiter(self.cmd_args)
        die_if_unbearable(args, CmdArgs)

        if isinstance(args, str):
            args = [args]

        # 2. Validation
        if self.guards:
            await self._validate_guards(*self.guards)

        # 3. Start Process
        logger.debug(f"Spawning {self.binary_path} with args: {args}")
        self.process = await asyncio.create_subprocess_exec(
            self.binary_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        # 4. Build the Stream Graph (Definition Phase)
        # We pass the process reference so the stream can write back to stdin
        merged_stream_op = self._build_pipeline(self.process)

        # 5. Enter the Stream Context (Activation Phase)
        # This spawns the background merger tasks safely
        active_iterator = await self.stack.enter_async_context(merged_stream_op.stream())

        # 6. Create the Handle
        handle = RunningProcess(
            process=self.process,
            process_streams=active_iterator
        )

        # 7. Initial Write (if any)
        if self.fixed_input:
            await handle.write(self.fixed_input)

        return handle

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 1. Stop the Streamer (Cancels background tasks)
        await self.stack.aclose()

        # 2. Stop the Process
        if self.process and self.process.returncode is None:
            if self.process.stdin:
                self.process.stdin.close()

            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def _process_responders(self, process: asyncio.subprocess.Process, chunk: bytes, channel: OutputChannel):
        """Runs all responders and writes back to stdin if they reply."""
        if not self.responders or not process.stdin:
            return

        for responder in self.responders:
            response = responder(chunk, channel)
            if inspect.isawaitable(response):
                response = await response

            if response is not None:
                try:
                    process.stdin.write(response)
                    # We usually don't drain here to avoid slowing down the read loop
                    # significantly, but for safety/correctness with pipes:
                    await process.stdin.drain()
                except BrokenPipeError:
                    pass

    def _build_pipeline(self, process: asyncio.subprocess.Process) -> aiostream.core.Stream:
        """Constructs the aiostream graph without starting it."""
        sources: list[aiostream.core.Stream] = []

        def channel_tagger(process: asyncio.subprocess.Process, channel: OutputChannel) -> Callable[
            [bytes], AwaitableMaybe[ProcessOutput]]:
            """Creates the mapping function that converts bytes to ProcessOutput."""

            async def transformer(chunk: bytes) -> ProcessOutput:
                # If we have responders, we process them here "side-effect style"
                if self.responders:
                    await self._process_responders(process, chunk, channel)

                return ProcessOutput(chunk, channel)

            return transformer

        async def reader_chunker(
                stream: asyncio.StreamReader, output_channel: OutputChannel,
                chunker: StreamChunker) -> AsyncIterator[bytes]:
            while True:
                chunk = await safe_awaiter(chunker(stream, output_channel))
                match chunk:
                    case bytes():
                        yield chunk
                    case ChunkSignal.SKIP:
                        continue
                    case ChunkSignal.EOF:
                        break

        # Helper to attach responders/transformers to a raw stream
        def attach_channel(raw_stream: asyncio.StreamReader, channel: OutputChannel) -> aiostream.core.Stream:
            # 1. Chunking (if needed) - assuming _stream_iterator applies chunking
            # If _stream_iterator returns an AsyncIterator, aiostream accepts it.
            if self.chunker:
                source = reader_chunker(raw_stream, channel, self.chunker)
            else:
                source = raw_stream

            # 2. Map: Convert bytes -> ProcessOutput AND handle responders
            # We use 'async_map' because we might need to await responders
            return aiostream.stream.map(source, channel_tagger(process, channel))

        if process.stdout:
            sources.append(attach_channel(process.stdout, OutputChannel.STDOUT))

        if process.stderr:
            sources.append(attach_channel(process.stderr, OutputChannel.STDERR))

        # 3. Merge streams
        merged = aiostream.stream.merge(*sources)

        return merged

    async def start_background(self, responders: Iterable[Responder] | None = None) -> int | None:
        async with self as service:
            async for event in service:
                if responders:
                    await service.write_from_responders(event.data, event.channel, responders)
                logger.debug(event)
            return service.process.returncode
