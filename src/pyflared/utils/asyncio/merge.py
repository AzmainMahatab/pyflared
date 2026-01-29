import asyncio
import inspect
from collections.abc import AsyncIterable, AsyncIterator, Callable, Awaitable
from typing import final, overload


class StopSentinel: pass


STOP_SIGNAL = StopSentinel()


@final
class StreamError:
    def __init__(self, error: Exception) -> None:
        self.error = error


# Overloads ensure proper return types based on whether a transformer is provided
@overload
def merge_async_iterators[T](
        *iterables: AsyncIterable[T],
) -> AsyncIterator[T]: ...


@overload
def merge_async_iterators[T, R](
        *iterables: AsyncIterable[T],
        transformer: Callable[[T], R | Awaitable[R]]
) -> AsyncIterator[R]: ...


async def merge_async_iterators[T, R](
        *iterables: AsyncIterable[T],
        transformer: Callable[[T], R | Awaitable[R]] | None = None
) -> AsyncIterator[T | R]:
    """
    Safely merges multiple AsyncIterables concurrently, applying an optional transformation.

    Parameters:
        *iterables: The asynchronous iterables to combine concurrently. Passes as variable positional arguments.
        transformer: An optional function (synchronous or asynchronous) applied to each item.
                     It takes an item of type T and returns type R. The transformation happens
                     concurrently within the individual consumer tasks before reaching the queue.
    """
    if not iterables:
        raise ValueError("At least one iterable is required.")

    # Properly defined inner async method to handle the transformation type check
    async def apply_transform(item: T) -> R | T:
        if transformer is None:
            return item

        result = transformer(item)
        if inspect.isawaitable(result):
            return await result
        return result

    # Fast-path for a single iterable
    if len(iterables) == 1:
        async for i in iterables[0]:
            yield await apply_transform(i)
        return

    queue: asyncio.Queue[T | R | StreamError | StopSentinel] = asyncio.Queue(maxsize=len(iterables))
    active_tasks: int = len(iterables)

    async def consume(gen: AsyncIterable[T]) -> None:
        try:
            async for i in gen:
                transformed_item = await apply_transform(i)
                await queue.put(transformed_item)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await queue.put(StreamError(e))

        await queue.put(STOP_SIGNAL)

    async with asyncio.TaskGroup() as tg:
        for g in iterables:
            _ = tg.create_task(consume(g))

        while active_tasks > 0:
            item = await queue.get()

            if isinstance(item, StopSentinel):
                active_tasks -= 1
            elif isinstance(item, StreamError):
                raise item.error
            else:
                yield item
