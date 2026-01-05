import inspect

import wrapt

from pyflared.binary.decorator import Guard, CommandError


class BinaryApp:
    def __init__(self, binary_path: str):
        self.binary_path = binary_path

    @classmethod
    async def _check_guards(cls, *guards: Guard):
        for guard in guards:
            result = guard()
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise CommandError(f"Precondition failed: {guard.__name__}")

    def daemon(self, *guards: Guard):
        @wrapt.decorator
        async def wrapper(wrapped, instance, args, kwargs):
            await self._check_guards(*guards)

            # Arg building
            if inspect.iscoroutinefunction(wrapped):
                cmd_args = await wrapped(*args, **kwargs)
            else:
                cmd_args = wrapped(*args, **kwargs)


            result = wrapped(*args, **kwargs)
            return result

        return wrapper
