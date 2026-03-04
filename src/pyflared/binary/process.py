import asyncio
import contextlib
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass, field
from types import TracebackType
from typing import override

from pyflared.binary.process_instance import ProcessInstance
from loguru import logger

from pyflared.shared.types import (
    CmdArg,
    CmdArgs,
    ProcessCmd,
    CommandError,
    Guard,
    Responder,
    StreamChunker, BinaryCallable,
)
from pyflared.utils.asyncio.wait import safe_awaiter
from pyflared.utils.type_check import is_of_type


@dataclass
class ProcessContext(contextlib.AbstractAsyncContextManager[ProcessInstance]):
    """
    Manages the lifecycle of a subprocess and its associated IO streams.
    """
    binary_path: BinaryCallable
    cmd_args: ProcessCmd

    # Configuration
    guards: list[Guard] | None = None
    stream_chunker: StreamChunker | None = None

    fixed_input: str | None = None
    default_responders: list[Responder] | None = None

    # Internal State # field is used for non-constructor properties
    process: asyncio.subprocess.Process | None = field(default=None, init=False)
    running_process: ProcessInstance | None = field(default=None, init=False)

    async def _validate_guards(self):
        if self.guards:
            for guard in self.guards:
                if not await safe_awaiter(guard()):
                    raise CommandError(f"Precondition failed: {guard.__name__}")

    @override
    async def __aenter__(self) -> ProcessInstance:
        if self.running_process:
            raise RuntimeError("Process already started once")

        # 1. Prepare Args
        ags = self.cmd_args
        if is_of_type(ags, AsyncGenerator[CmdArgs, None]):
            ags = await anext(ags)

        args = await safe_awaiter(ags)
        if is_of_type(args, CmdArg):
            args = [args]

        # 2. Validation
        if self.guards:
            await self._validate_guards()

        # 3. Start Process
        logger.debug(f"Spawning {self.binary_path} with args: {args}")
        process = await asyncio.create_subprocess_exec(
            self.binary_path(), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        self.running_process = ProcessInstance(process, self.fixed_input, self.stream_chunker, self.default_responders)
        return self.running_process

    @override
    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None,
                        traceback: TracebackType | None, /):
        if not self.running_process:
            return

        await self.running_process.stop_gracefully()
        if isinstance(self.cmd_args, AsyncGenerator):
            # This is to execute the cleanup code after the process is finished
            await self.cmd_args.aclose()

    # `responders` is also a good place to add logger if needed
    async def start_background(self, responders: Iterable[Responder] | None = None) -> int | None:
        async with self as service:
            async for event in service:
                if responders:
                    await service.write_from_responders(event.data, event.channel, responders)
                # logger.debug(event)
            return await service.wait()
