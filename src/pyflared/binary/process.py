import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import AsyncIterable, AsyncIterator, AsyncContextManager, Iterable, Callable, Self

import aiostream
from beartype.door import die_if_unbearable

from pyflared.shared.types import OutputChannel, StreamChunker, Responder, CmdArg, CmdArgs, Guard, \
    ProcessOutput, AwaitableMaybe, ChunkSignal, CommandError
from pyflared.utils.async_helper import safe_awaiter

type FinalCmdFun[**P] = Callable[P, ProcessContext]

type Converter[R] = Callable[[ProcessContext], R]
type Mutator = Callable[[ProcessOutput], AwaitableMaybe[bytes]]

from loguru import logger


@dataclass
class _ProcessWriter:
    process: asyncio.subprocess.Process

    async def write(self, data: AwaitableMaybe[str | bytes]) -> None:
        """write to stdin."""
        if not self.process.stdin:
            return
        try:
            data = await safe_awaiter(data)
            self.process.stdin.write(data)
            await self.process.stdin.drain()
        except BrokenPipeError:
            pass

    async def write_line(self, data: AwaitableMaybe[str]):
        await self.write(data + "\n")

    async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
        for responder in responders:
            response = await safe_awaiter(responder(chunk, channel))
            if response is not None:
                await self.write(response)


@dataclass
class _StreamMaker(_ProcessWriter):
    chunker: StreamChunker | None = None
    responders: list[Responder] | None = None

    async def stream_context(self, fixed_input: str | None, ) -> aiostream.core.Stream:
        """Constructs the aiostream graph without starting it."""
        if fixed_input:
            logger.debug(f"Sending fixed input: {fixed_input}")
            await self.write(fixed_input)

        sources: list[aiostream.core.Stream] = []

        def channel_tagger(channel: OutputChannel) -> Callable[
            [bytes], AwaitableMaybe[ProcessOutput]]:
            """Creates the mapping function that converts bytes to ProcessOutput."""

            async def transformer(chunk: bytes) -> ProcessOutput:
                if self.responders:
                    await self.write_from_responders(chunk, channel, self.responders)

                # if self.log_err_stream and channel == OutputChannel.STDERR:
                # if channel == OutputChannel.STDERR:
                #     logger.debug(chunk.decode())
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
            if self.chunker:
                source = reader_chunker(raw_stream, channel, self.chunker)
            else:
                source = raw_stream

            # 2. Map: Convert bytes -> ProcessOutput AND handle responders
            return aiostream.stream.map(source, channel_tagger(channel))

        if self.process.stdout:
            sources.append(attach_channel(self.process.stdout, OutputChannel.STDOUT))

        if self.process.stderr:
            sources.append(attach_channel(self.process.stderr, OutputChannel.STDERR))

        # 3. Merge streams
        merged = aiostream.stream.merge(*sources)
        return merged


@dataclass()
class ProcessInstance(_ProcessWriter, AsyncIterable[ProcessOutput]):
    merged_iterable: AsyncIterable[ProcessOutput]

    def __aiter__(self):
        return self.merged_iterable

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
        async for output in self:
            if mutator:
                await target.write(mutator(output))
            elif output.channel == OutputChannel.STDOUT:
                await target.write(output.data)

    async def drain_wait(self) -> int:
        """Drains all output until the process completes."""
        async for _ in self:
            pass
        return await self.process.wait()

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    async def stop_gracefully(self):
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
class ProcessContext(AsyncContextManager[ProcessInstance]):
    """
    Manages the lifecycle of a subprocess and its associated IO streams.
    """
    binary_path: CmdArg
    cmd_args: CmdArgs

    # Configuration
    guards: list[Guard] | None = None
    stream_chunker: StreamChunker | None = None

    fixed_input: str | None = None
    responders: list[Responder] | None = None

    # Internal State
    process: asyncio.subprocess.Process | None = field(default=None, init=False)
    running_process: ProcessInstance | None = field(default=None, init=False)
    stack: contextlib.AsyncExitStack = field(default_factory=contextlib.AsyncExitStack, init=False)

    async def _validate_guards(self):
        if self.guards:
            for guard in self.guards:
                if not await safe_awaiter(guard()):
                    raise CommandError(f"Precondition failed: {guard.__name__}")

    async def __aenter__(self) -> ProcessInstance:
        if self.running_process:
            raise RuntimeError("Process already started once")

        # 1. Prepare Args
        args = await safe_awaiter(self.cmd_args)
        die_if_unbearable(args, CmdArgs)

        if isinstance(args, str):
            args = [args]

        # 2. Validation
        if self.guards:
            await self._validate_guards()

        # 3. Start Process
        logger.debug(f"Spawning {self.binary_path} with args: {args}")
        process = await asyncio.create_subprocess_exec(
            self.binary_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        stream_maker = _StreamMaker(process, chunker=self.stream_chunker, responders=self.responders)
        x1 = await stream_maker.stream_context(self.fixed_input)
        merged_stream = await self.stack.enter_async_context(x1.stream())
        self.running_process = ProcessInstance(process, merged_stream)
        return self.running_process

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.running_process:
            return
        await self.stack.aclose()
        await self.running_process.stop_gracefully()

    # `responders` is also a good place to add logger if needed
    async def start_background(self, responders: Iterable[Responder] | None = None) -> int | None:
        async with self as service:
            async for event in service:
                if responders:
                    await service.write_from_responders(event.data, event.channel, responders)
                # logger.debug(event)
                # print(event.data)
            return service.returncode
