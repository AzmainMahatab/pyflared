import inspect
from collections.abc import Awaitable
from typing import overload


@overload
def safe_awaiter[T](a: Awaitable[T]) -> Awaitable[T]: ...


@overload
def safe_awaiter[T](a: T) -> Awaitable[T]: ...


async def safe_awaiter(a: object) -> object:
    if inspect.isawaitable(a):
        return await a
    return a
