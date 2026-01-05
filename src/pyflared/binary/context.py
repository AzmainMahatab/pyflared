import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Callable, Iterable, AsyncIterator, AsyncIterable, AsyncContextManager

import aiostream
from beartype.door import die_if_unbearable
from rich.pretty import pretty_repr

from pyflared.types import ProcessOutput, ProcessOutputFilter, Responder, OutputChannel, Guard, CmdArg, CmdArgs, \
    StreamChunker, CommandError, AwaitableMaybe
from pyflared.utils.async_helper import safe_awaiter

type ProcessContext = AsyncContextManager[ProcessHandle2]
type FinalCmdFun[**P] = Callable[P, ProcessContext2]

type Converter[R] = Callable[[ProcessContext2], R]
type Mutator = Callable[[ProcessOutput], AwaitableMaybe[bytes]]

logger = logging.getLogger(__name__)


async def _validate_guards(guards: Iterable[Guard]):
    for guard in guards:
        result = guard()
        if inspect.isawaitable(result):
            result = await result
        if not result:
            raise CommandError(f"Precondition failed: {guard.__name__}")


async def _stream_iterator(
        stream: asyncio.StreamReader, output_channel: OutputChannel,
        stream_chunker: StreamChunker) -> AsyncIterator[bytes]:
    while True:
        if chunk := await stream_chunker(stream, output_channel):
            yield chunk
        else:  # End of stream
            break


# async def mutate(source: AsyncIterator[ProcessOutput],) -> AsyncIterator[ProcessOutput]:
#     async for output in source:
#         if mutated := await mutator(output.data, output.channel):
#             yield ProcessOutput(mutated, output.channel, output.timestamp))


@dataclass
class ProcessHandle2(AsyncIterable[ProcessOutput]):
    process: asyncio.subprocess.Process
    chunker: StreamChunker | None = None
    out_filter: ProcessOutputFilter | None = None
    responders: list[Responder] | None = None

    # def add_responder(self, responder: Responder):
    #     self.responders.append(responder)

    async def write(self, data: str | bytes):
        """Safe write to stdin"""
        if not self.process.stdin:
            return

        try:
            self.process.stdin.write(data)
            if isinstance(data, str) and not data.endswith("\n"):
                self.process.stdin.write(b"\n")
            await self.process.stdin.drain()
        except BrokenPipeError:
            pass  # Process might have closed already

    def __aiter__(self) -> AsyncIterator[ProcessOutput]:
        if out_filter := self.out_filter:
            return self.filterator(out_filter)
        else:
            return self.mixed_stream()

    async def filterator(self, fr: ProcessOutputFilter) -> AsyncIterator[ProcessOutput]:
        async for output in self.mixed_stream():
            if filtered := fr(output):
                yield filtered

    async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
        for responder in responders:
            response = responder(chunk, channel)
            if inspect.isawaitable(response):
                response = await response
            if response is not None:
                await self.write(response)

    def mixed_stream(self) -> AsyncIterator[ProcessOutput]:
        """Yields both stdout and stderr mixed."""

        def channel_tagger(channel: OutputChannel) -> Callable[[bytes], AwaitableMaybe[ProcessOutput] | ProcessOutput]:
            async def transformer(chunk: bytes) -> ProcessOutput:
                if self.responders:
                    await self.write_from_responders(chunk, channel, self.responders)
                return ProcessOutput(chunk, channel)

            return transformer

        sources: list[AsyncIterator[ProcessOutput]] = []

        if self.process.stdout:
            sout = _stream_iterator(self.process.stdout, OutputChannel.STDOUT,
                                    self.chunker) if self.chunker else self.process.stdout

            tagged_stdout = aiostream.stream.map(sout, channel_tagger(OutputChannel.STDOUT))
            sources.append(tagged_stdout)

        if self.process.stderr:
            serr = _stream_iterator(self.process.stderr, OutputChannel.STDERR,
                                    self.chunker) if self.chunker else self.process.stderr

            tagged_stderr = aiostream.stream.map(serr, channel_tagger(OutputChannel.STDERR))
            sources.append(tagged_stderr)

        stream = aiostream.stream.merge(*sources)
        return aiter(stream)

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


@dataclass
class ProcessContext2(AsyncContextManager[ProcessHandle2]):
    binary_path: CmdArg
    cmd_args: CmdArgs
    guards: list[Guard] | None = None
    fixed_input: str | None = None
    stream_chunker: StreamChunker | None = None
    process: asyncio.subprocess.Process | None = None
    responders: list[Responder] | None = None

    async def __aenter__(self) -> ProcessHandle2:
        args = await safe_awaiter(self.cmd_args)
        logger.debug(type(args))
        logger.debug(f"Running {self.binary_path} with {pretty_repr(args)}")

        die_if_unbearable(args, CmdArgs)
        if isinstance(args, str):
            args = [args]

        if self.guards:
            await _validate_guards(*self.guards)
        self.process = await asyncio.create_subprocess_exec(
            self.binary_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE)

        process_handle = ProcessHandle2(self.process, chunker=self.stream_chunker, responders=self.responders)
        if self.fixed_input:
            await process_handle.write(self.fixed_input)

        return process_handle

    async def __aexit__(self, exc_type, exc_value, traceback):
        if not (process := self.process) or process.returncode is not None:  # process.returncode None if still running
            return

        process.stdin.close()
        logger.info("Terminating process...")
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.info("Force killing process...")
            process.kill()
            await process.wait()

    async def start_background(self, responders: Iterable[Responder] | None = None) -> int | None:
        async with self as service:
            async for event in service:
                if responders:
                    await service.write_from_responders(event.data, event.channel, responders)
                logger.debug(event)
            return service.process.returncode


async def gather_stdout(process_context: ProcessContext2) -> str:
    async with process_context as handle:
        output_chunks: list[bytes] = []
        async for chunk in handle:
            output_chunks.append(chunk.data)
        return b"".join(output_chunks).decode()  # type: ignore
