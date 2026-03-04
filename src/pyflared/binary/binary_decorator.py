from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any

from pyflared.binary.process import ProcessContext
from pyflared.shared.types import Guard, OutputChannel, Responder, StreamChunker, BinaryCallable, ProcessCmd

type AsyncFunction[**P, R] = Callable[P, Coroutine[Any, Any, R]]  # pyright: ignore[reportExplicitAny]
type ProcessTargetable[**P] = Callable[P, ProcessCmd]
type FinalCmdFun[**P] = Callable[P, ProcessContext]


class BinaryApp:

    def __init__(self, binary_path: BinaryCallable):
        self.binary_path: BinaryCallable = binary_path

    def daemon[**P](
            self, guards: list[Guard] | None = None,
            stream_chunker: StreamChunker | None = None,  # This is also a good place to add logger if needed
            fixed_input: str | None = None,
            responders: list[Responder] | None = None,
    ) -> Callable[[ProcessTargetable[P]], FinalCmdFun[P]]:
        def decorator(func: ProcessTargetable[P]) -> FinalCmdFun[P]:
            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> ProcessContext:
                cmd_args = func(*args, **kwargs)

                return ProcessContext(
                    binary_path=self.binary_path,
                    cmd_args=cmd_args,
                    stream_chunker=stream_chunker,
                    fixed_input=fixed_input,
                    guards=guards,
                    default_responders=responders,
                )

            return wrapper

        return decorator

    def instant[**P](
            self,
            fixed_input: str | None = None,
            stream_chunker: StreamChunker | None = None,
            responders: list[Responder] | None = None,
            guards: list[Guard] | None = None,
    ) -> Callable[[ProcessTargetable[P]], Callable[P, Awaitable[str]]]:
        actual_converter = self.concatenate_stdout

        """
        Decorates a function to produce a ProcessContext2 via self.daemon,
        then immediately awaits the provided converter to return a result.
        """
        # 1. Reuse the existing daemon logic to create the context-provider decorator
        daemon_decorator = self.daemon(
            fixed_input=fixed_input,
            stream_chunker=stream_chunker,
            responders=responders,
            guards=guards,
        )

        def decorator(func: ProcessTargetable[P]) -> Callable[P, Awaitable[str]]:
            # 2. Wrap the user's function with daemon to get the sync context generator
            # ctx_factory signature: (*args, **kwargs) -> ProcessContext2
            ctx_factory = daemon_decorator(func)

            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
                # 3. Generate the context synchronously
                process_context = ctx_factory(*args, **kwargs)

                # 4. Await the converter to get the fast result
                return await actual_converter(process_context)

            return wrapper

        return decorator

    @classmethod
    async def concatenate_stdout(cls, process_context: ProcessContext) -> str:
        sout_buffer: list[bytes] = []
        err_buffer: list[bytes] = []

        def concatenate(data: bytes, channel: OutputChannel):
            if channel == OutputChannel.STDOUT:
                sout_buffer.append(data)
            else:
                err_buffer.append(data)

        returncode = await process_context.start_background([concatenate])

        if returncode != 0:
            raise RuntimeError(
                f"Command failed with exit code {returncode}. Stderr: {b''.join(err_buffer).decode()}, Stdout: {b''.join(sout_buffer).decode()}")
        return b"".join(sout_buffer).decode()
