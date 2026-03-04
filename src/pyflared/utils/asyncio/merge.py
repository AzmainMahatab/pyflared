import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import final


class StopSentinel: pass


STOP_SIGNAL = StopSentinel()


@final
class StreamError:
    def __init__(self, error: Exception) -> None:
        self.error = error


async def merge_async_iterators[T](*iterables: AsyncIterable[T]) -> AsyncIterator[T]:
    """
    Safely merges multiple AsyncIterables concurrently.

    Parameters:
        *iterables: The asynchronous iterables to combine.
    """
    if not iterables:
        raise ValueError("At least one iterable is required.")

    if len(iterables) == 1:
        async for i in iterables[0]:
            yield i
        return

    queue: asyncio.Queue[T | StreamError | StopSentinel] = asyncio.Queue(maxsize=len(iterables))
    active_tasks: int = len(iterables)

    # gen is now typed as AsyncIterable to match the parameters
    async def consume(gen: AsyncIterable[T]) -> None:
        try:
            async for i in gen:
                await queue.put(i)
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
