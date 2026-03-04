import functools
from collections.abc import AsyncIterable, Awaitable, AsyncIterator
from typing import Callable


# def yield_from_async[**P, T](
#         func: Callable[P, Awaitable[AsyncIterable[T]] | None]
# ) -> Callable[P, AsyncIterator[T]]:
#     """
#     Converts a coroutine returning an AsyncIterable into an AsyncIterator.
#     """
#
#     @functools.wraps(func)
#     async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
#         if coroutined_async_iterator := func(*args, **kwargs):
#             async for item in await coroutined_async_iterator:
#                 yield item
#
#     return wrapper

# def yield_from_async[**P, T](
#         func: Callable[P, Awaitable[AsyncIterable[T]]]
# ) -> Callable[P, AsyncIterator[T]]:
#     """
#     Converts a coroutine returning an AsyncIterable into an AsyncIterator.
#     """
#
#     @functools.wraps(func)
#     async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
#         iterable = await func(*args, **kwargs)
#         async for item in iterable:
#             yield item
#
#     return wrapper

def yield_from_async[**P, T](
        func: Callable[P, Awaitable[AsyncIterable[T] | None]]
) -> Callable[P, AsyncIterator[T]]:
    """
    Converts a coroutine returning an AsyncIterable into an AsyncIterator.
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
        if iterable := await func(*args, **kwargs):
            async for item in iterable:
                yield item

    return wrapper


async def safe_paginator_with_setup[T](
        iterable: AsyncIterable[T],
        setup_func: Callable[[], Awaitable[None]]
) -> AsyncIterator[T]:
    """
    A generic generator that triggers the first fetch,
    runs setup_func() on success, and yields all items cleanly.
    API-specific errors naturally bubble up to the caller.
    """
    iterator = aiter(iterable)

    try:
        # Trigger the first fetch.
        # ANY network/API errors will safely bubble up from here!
        first_item = await anext(iterator)

    except StopAsyncIteration:
        # Normal behavior for an empty iterable (zero results)
        return

    # No errors occurred! Safe to run the setup logic.
    await setup_func()

    # Yield the first item
    yield first_item

    # Proxy the remainder of the items seamlessly
    async for item in iterator:
        yield item
