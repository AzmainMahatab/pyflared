import asyncio
import datetime
import inspect
import os
from asyncio import Task
from contextlib import asynccontextmanager
from enum import StrEnum, auto
from functools import wraps, partial
from typing import Callable, Awaitable, Iterable, AsyncGenerator, AsyncIterator, NamedTuple, AsyncIterable, \
    AsyncContextManager, Concatenate
import aiostream
from aiostream import await_
from dill import logger

from pyflared.binary.trash.B import logger


class CommandError(Exception):
    pass


class OutputChannel(StrEnum):
    STDOUT = auto()
    STDERR = auto()


type Response = bytes | str | None
type Responder = Callable[[bytes, OutputChannel], Response | Awaitable[Response]]


def responder_proxy(func: Responder) -> Responder:
    """Identity decorator to validate signatures."""
    return func


type StreamChunker = Callable[[asyncio.StreamReader, OutputChannel], Response | Awaitable[Response]]

type Guard = Callable[[], bool | Awaitable[bool]]


class ProcessOutput(NamedTuple):
    data: bytes
    channel: OutputChannel
    timestamp: datetime.datetime = datetime.datetime.now(datetime.UTC)


type CmdArg = str | bytes | os.PathLike[str] | os.PathLike[bytes]
type CmdArgs = Iterable[CmdArg] | Awaitable[Iterable[CmdArg]]

type ProcessContext = AsyncContextManager[ProcessHandle]

type CmdTargetable[**P] = Callable[P, CmdArgs]
type FinalCmdFun[**P] = Callable[P, ProcessContext]
type FinalCmdFun2[**P] = Callable[Concatenate[list[Responder], P], ProcessContext]


class BinaryApp:
    def __init__(self, binary_path: str):
        self.binary_path = binary_path

    @classmethod
    async def _validate_guards(cls, *guards: Guard):
        for guard in guards:
            result = guard()
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise CommandError(f"Precondition failed: {guard.__name__}")

    def daemon[**P](
            self, fixed_input: str | None = None,
            stream_chunker: StreamChunker | None = None,
            guards: list[Guard] = None) -> Callable[[CmdTargetable[P]], FinalCmdFun2[P]]:

        def decorator(func: CmdTargetable[P]):
            @wraps(func)
            @asynccontextmanager
            async def wrapper(responders: list[Responder] | None = None, *args: P.args, **kwargs: P.kwargs):

                await self._validate_guards(*guards)

                # Arg building
                if inspect.iscoroutinefunction(func):
                    cmd_args = await func(*args, **kwargs)
                else:
                    cmd_args = func(*args, **kwargs)

                process = await asyncio.create_subprocess_exec(
                    self.binary_path, *cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE)

                try:
                    ph = ProcessHandle(process, responders=responders, chunker=stream_chunker)
                    if fixed_input:
                        await ph.write(fixed_input)
                    yield aiter(ph)
                finally:
                    if process.returncode is None:
                        process.stdin.close()
                        logger.info("Terminating process...")
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            logger.info("Force killing process...")
                            process.kill()
                            await process.wait()

            return wrapper

        return decorator

    def instant[**P](self):
        pass


async def _stream_iterator(
        stream: asyncio.StreamReader, output_channel: OutputChannel,
        stream_chunker: StreamChunker) -> AsyncIterator[bytes]:
    while True:
        if chunk := await stream_chunker(stream, output_channel):
            yield chunk
        else:  # End of stream
            break


class ProcessHandle(AsyncIterable[ProcessOutput]):
    _responders: list[Responder] = []

    def __init__(self, process: asyncio.subprocess.Process,
                 chunker: StreamChunker | None = None,
                 responders: list[Responder] | None = None):
        self.process = process
        self._chunker = chunker

        if responders:
            self._responders.extend(responders)

    def add_responder(self, r: Responder):
        self._responders.append(r)

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
        """Yields both stdout and stderr mixed."""

        def channel_tagger(channel: OutputChannel) -> Callable[[bytes], Awaitable[ProcessOutput] | ProcessOutput]:
            async def transformer(chunk: bytes) -> ProcessOutput:
                for responder in self._responders:
                    response = responder(chunk, channel)
                    if inspect.isawaitable(response):
                        response = await response
                    if response is not None:
                        await self.write(response)
                return ProcessOutput(chunk, channel)

            return transformer

        sources: list[AsyncIterator[ProcessOutput]] = []

        if self.process.stdout:
            sout = _stream_iterator(self.process.stdout, OutputChannel.STDOUT,
                                    self._chunker) if self._chunker else self.process.stdout
            tagged_stdout = aiostream.pipe.map(sout, channel_tagger(OutputChannel.STDOUT))
            sources.append(tagged_stdout)

        if self.process.stderr:
            serr = _stream_iterator(self.process.stderr, OutputChannel.STDERR,
                                    self._chunker) if self._chunker else self.process.stderr

            tagged_stderr = aiostream.pipe.map(serr, channel_tagger(OutputChannel.STDERR))
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


cf = BinaryApp("cf")


def confirm_token() -> bool:
    return True


@cf.daemon(guards=[confirm_token])
def x1(s: int) -> list[str]:
    pass


y1 = x1(s=2, respon)


# class ProcessHandle(AsyncIterable[ProcessOutput]):
#
#     def __init__(self, process: asyncio.subprocess.Process):
#         self._process = process
#
#     def __aiter__(self) -> AsyncIterator[ProcessOutput]:
#         """Yields both stdout and stderr mixed together safely."""
#
#         def add_channel_tag(channel: OutputChannel):
#             def transformer(chunk: bytes) -> ProcessOutput:
#                 return ProcessOutput(chunk, channel)
#
#             return aiostream.pipe.map(transformer)
#
#         sources: list[AsyncIterator[ProcessOutput]] = []
#
#         if self._process.stdout:
#             raw_stdout = aiostream.stream.iterate(self._process.stdout)
#             tagged_stdout = raw_stdout | add_channel_tag(OutputChannel.STDOUT)
#             sources.append(tagged_stdout)
#
#         if self._process.stderr:
#             raw_stderr = aiostream.stream.iterate(self._process.stderr)
#             tagged_stderr = raw_stderr | add_channel_tag(OutputChannel.STDERR)
#             sources.append(tagged_stderr)
#
#         stream = aiostream.stream.merge(*sources)
#         return aiter(stream)
#
#     async def stdout_only(self) -> AsyncIterator[bytes]:
#         """Yields only stdout, but drains stderr."""
#         async for output in self:
#             if output.channel == OutputChannel.STDOUT:
#                 yield output.data
#
#     async def stderr_only(self) -> AsyncIterator[bytes]:
#         """Yields only stderr, but drains stdout."""
#         async for output in self:
#             if output.channel == OutputChannel.STDERR:
#                 yield output.data
#
#     async def drain_wait(self) -> None:
#         """Drains all output until the process completes."""
#         async for _ in self:
#             pass
#         await self._process.wait()


class BinaryApp:
    def __init__(self, binary_path: str):
        self.binary_path = binary_path

    def daemon(self, guards: List[Guard] = None, responders: List[Responder] = None):
        """
        Decorator for defining commands.
        :param guards: List of functions to check before starting.
        :param responders: List of static auto-reply functions.
        """
        if guards is None: guards = []
        if responders is None: responders = []

        def decorator(func: Callable[P, Union[List[str], Awaitable[List[str]]]]):
            @wraps(func)
            @asynccontextmanager
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[ProcessStream, None]:

                # 1. Run Preconditions (Guards)
                for guard in guards:
                    result = guard()
                    if inspect.isawaitable(result):
                        result = await result
                    if result is False:
                        raise CommandError(f"Precondition failed: {guard.__name__}")

                # 2. Build Arguments
                if inspect.iscoroutinefunction(func):
                    cmd_args = await func(*args, **kwargs)
                else:
                    cmd_args = func(*args, **kwargs)

                full_cmd = [self.binary_path] + cmd_args
                print(f"🚀 Executing: {' '.join(full_cmd)}")

                # 3. Start Process (With Separated Pipes)
                process = await asyncio.create_subprocess_exec(
                    *full_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,  # Keep separate!
                )

                stream = ProcessStream(process)

                # Register static responders (from decorator)
                for r in responders:
                    stream.add_responder(r)

                try:
                    yield stream
                finally:
                    # 4. Robust Cleanup
                    if process.returncode is None:
                        # print("🛑 Terminating process...")
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()

            return wrapper

        return decorator


app = BinaryApp(sys.executable)


# --- 3. Define Commands ---

# Command A: Simulates a tool that asks for input
# Note: We use '-u' for unbuffered python output so we see it instantly
@app.daemon(responders=[auto_confirm])
def interactive_tool(name: str) -> List[str]:
    pass
