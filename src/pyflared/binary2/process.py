import asyncio
import contextlib
import inspect
import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterable, AsyncIterator, AsyncContextManager, Iterable, Callable, Protocol

import aiostream
from beartype.door import die_if_unbearable

from pyflared.binary.context import Mutator
from pyflared.types import OutputChannel, StreamChunker, Responder, CmdArg, CmdArgs, Guard, \
    ProcessOutput, AwaitableMaybe, ChunkSignal, CommandError
from pyflared.utils.async_helper import safe_awaiter

logger = logging.getLogger(__name__)


class ProcessInstance(AsyncIterable[ProcessOutput], Protocol):

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

    @abstractmethod
    async def write(self, data: AwaitableMaybe[str | bytes]) -> None:
        ...

    async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
        for responder in responders:
            response = await safe_awaiter(responder(chunk, channel))
            if response is not None:
                await self.write(response)

    async def pipe_to(self, target: RunningProcess, mutator: Mutator | None = None) -> None:
        async for output in self:
            if mutator:
                await target.write(mutator(output))
            elif output.channel == OutputChannel.STDOUT:
                await target.write(output.data)

    @abstractmethod
    async def drain_wait(self) -> int:
        ...

    @abstractmethod
    @property
    def returncode(self) -> int | None:
        ...


@dataclass()
class RunningProcess(ProcessInstance):
    """
    A safe, active handle to a running process.
    """
    process: asyncio.subprocess.Process
    chunker: StreamChunker | None = None
    responders: list[Responder] | None = None

    stack: contextlib.AsyncExitStack = field(default_factory=contextlib.AsyncExitStack, init=False)
    process_streams: AsyncIterator[ProcessOutput] | None = None

    def __aiter__(self) -> AsyncIterator[ProcessOutput]:
        if not self.process_streams:
            raise RuntimeError("Process streams are not initialized.")
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

    async def drain_wait(self) -> int:
        """Drains all output until the process completes."""
        async for _ in self:
            pass
        return await self.process.wait()

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    def _build_pipeline(self) -> aiostream.core.Stream:
        """Constructs the aiostream graph without starting it."""
        sources: list[aiostream.core.Stream] = []

        def channel_tagger(channel: OutputChannel) -> Callable[
            [bytes], AwaitableMaybe[ProcessOutput]]:
            """Creates the mapping function that converts bytes to ProcessOutput."""

            async def transformer(chunk: bytes) -> ProcessOutput:
                if self.responders:
                    await self.write_from_responders(chunk, channel, self.responders)

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
            return aiostream.stream.map(source, channel_tagger(channel))

        if self.process.stdout:
            sources.append(attach_channel(self.process.stdout, OutputChannel.STDOUT))

        if self.process.stderr:
            sources.append(attach_channel(self.process.stderr, OutputChannel.STDERR))

        # 3. Merge streams
        merged = aiostream.stream.merge(*sources)

        return merged

    async def activate(
            self, fixed_input: str | None, ):

        if fixed_input:
            await self.write(fixed_input)

        merged_stream = self._build_pipeline()
        self.process_streams = await self.stack.enter_async_context(merged_stream.stream())

    async def close(self):
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




@dataclass
class ProcessExecutor(AsyncContextManager[ProcessInstance]):
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
    running_process: RunningProcess | None = None

    @classmethod
    async def _validate_guards(cls, guards: Iterable[Guard]):
        for guard in guards:
            result = guard()
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise CommandError(f"Precondition failed: {guard.__name__}")

    async def __aenter__(self) -> ProcessInstance:
        if self.running_process:
            raise RuntimeError("Process already started once")

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

        self.running_process = RunningProcess(
            process=self.process,
            chunker=self.chunker,
            responders=self.responders,
        )

        await self.running_process.activate(self.fixed_input)

        return self.running_process

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.running_process:
            return
        await self.running_process.close()

    async def start_background(self, responders: Iterable[Responder] | None = None) -> int | None:
        async with self as service:
            async for event in service:
                if responders:
                    await service.write_from_responders(event.data, event.channel, responders)
                logger.debug(event)
            return service.returncode


# class P2(asyncio.subprocess.Process):
#     async def write(self, data: AwaitableMaybe[str | bytes]) -> None:
#         """write to stdin."""
#         if not self.stdin:
#             return
#         try:
#             data = await safe_awaiter(data)
#             self.stdin.write(data)
#             if isinstance(data, str) and not data.endswith("\n"):
#                 self.stdin.write(b"\n")
#             await self.stdin.drain()
#         except BrokenPipeError:
#             pass
#
#     async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
#         for responder in responders:
#             response = responder(chunk, channel)
#             if inspect.isawaitable(response):
#                 response = await response
#             if response is not None:
#                 await self.write(response)


@dataclass
class Intermediate:
    process: asyncio.subprocess.Process
    chunker: StreamChunker | None = None
    responders: list[Responder] | None = None

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

    def _build_pipeline(self) -> aiostream.core.Stream:
        """Constructs the aiostream graph without starting it."""
        sources: list[aiostream.core.Stream] = []

        def channel_tagger(channel: OutputChannel) -> Callable[
            [bytes], AwaitableMaybe[ProcessOutput]]:
            """Creates the mapping function that converts bytes to ProcessOutput."""

            async def transformer(chunk: bytes) -> ProcessOutput:
                if self.responders:
                    await self.write_from_responders(chunk, channel, self.responders)

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
            return aiostream.stream.map(source, channel_tagger(channel))

        if self.process.stdout:
            sources.append(attach_channel(self.process.stdout, OutputChannel.STDOUT))

        if self.process.stderr:
            sources.append(attach_channel(self.process.stderr, OutputChannel.STDERR))

        # 3. Merge streams
        merged = aiostream.stream.merge(*sources)

        return merged
