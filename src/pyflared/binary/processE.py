import logging
from functools import wraps
from typing import Callable, Awaitable, overload

from pyflared.binary.context import ProcessContext2, FinalCmdFun, gather_stdout
from pyflared.types import Guard, CmdArg, Responder, StreamChunker, CmdTargetable

logger = logging.getLogger(__name__)


def responder_proxy(func: Responder) -> Responder:
    """Identity decorator to validate signatures."""
    return func


# type AnyFunThatReturnsArgs = Callable[..., CmdArgs]


class BinaryApp:
    def __init__(self, binary_path: CmdArg):
        self.binary_path = binary_path

    def daemon[**P](
            self, fixed_input: str | None = None,
            stream_chunker: StreamChunker | None = None,
            responders: list[Responder] | None = None,
            guards: list[Guard] | None = None) -> Callable[[CmdTargetable[P]], FinalCmdFun[P]]:
        def decorator(func: CmdTargetable[P]) -> FinalCmdFun[P]:
            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> ProcessContext2:
                cmd_args = func(*args, **kwargs)

                process_context = ProcessContext2(
                    binary_path=self.binary_path,
                    cmd_args=cmd_args,
                    stream_chunker=stream_chunker,
                    fixed_input=fixed_input,
                    guards=guards,
                    responders=responders,
                )
                return process_context

            return wrapper

        return decorator

    @overload
    def instant[**P](
            self,
            fixed_input: str | None = None,
            stream_chunker: StreamChunker | None = None,
            responders: list[Responder] | None = None,
            guards: list[Guard] | None = None,
    ) -> Callable[[CmdTargetable[P]], Callable[P, Awaitable[str]]]:
        ...

    @overload
    def instant[**P, R](
            self,
            converter: Callable[[ProcessContext2], Awaitable[R]],
            fixed_input: str | None = None,
            stream_chunker: StreamChunker | None = None,
            responders: list[Responder] | None = None,
            guards: list[Guard] | None = None,
    ) -> Callable[[CmdTargetable[P]], Callable[P, Awaitable[R]]]:
        ...

    def instant[**P, R](
            self,
            converter: Callable[[ProcessContext2], Awaitable[R]] | None = None,  # Type as Optional internally
            fixed_input: str | None = None,
            stream_chunker: StreamChunker | None = None,
            responders: list[Responder] | None = None,
            guards: list[Guard] | None = None,
    ) -> Callable[[CmdTargetable[P]], Callable[P, Awaitable[R | str]]]:
        actual_converter = converter if converter is not None else gather_stdout

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

        def decorator(func: CmdTargetable[P]) -> Callable[P, Awaitable[R]]:
            # 2. Wrap the user's function with daemon to get the sync context generator
            # ctx_factory signature: (*args, **kwargs) -> ProcessContext2
            ctx_factory = daemon_decorator(func)

            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                # 3. Generate the context synchronously
                process_context = ctx_factory(*args, **kwargs)

                # 4. Await the converter to get the fast result
                return await actual_converter(process_context)

            return wrapper

        return decorator

# cf = BinaryApp("cf")
#
#
# def confirm_token() -> bool:
#     return True
#
#
# @cf.daemon(guards=[confirm_token])
# def x1(s: int) -> list[str]:
#     pass
#
#
# y1 = x1(s=2, )

# @cf.instant(guards=[confirm_token])
# def x2(s: int) -> list[str]:
#     pass
#
#
# sw = x2(s=3)
