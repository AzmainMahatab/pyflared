import inspect

from pyflared.shared.types import AwaitableMaybe


async def safe_awaiter[T](a: AwaitableMaybe[T]) -> T:
    if inspect.isawaitable(a):
        return await a
    return a
