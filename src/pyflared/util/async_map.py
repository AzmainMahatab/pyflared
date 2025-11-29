import asyncio
from contextlib import nullcontext
from typing import Callable, Awaitable, Iterable


async def async_dict[T, K, V](
        items: Iterable[T],
        key_func: Callable[[T], K],
        val_func: Callable[[T], Awaitable[V]],
        limit: int | None = None,
) -> dict[K, V]:
    """
    Concurrency-limited dictionary creator.
    """
    results: dict[K, V] = {}
    # nullcontext() works with 'async with' in Python 3.10+
    sem = asyncio.Semaphore(limit) if limit else nullcontext()

    async def worker(it: T):
        async with sem:
            # We await the value (expensive), then calculate key (cheap)
            # Or vice versa, depending on your logic.
            # Assuming key_func is synchronous and fast:
            k = key_func(it)
            v = await val_func(it)
            results[k] = v

    async with asyncio.TaskGroup() as tg:
        for item in items:
            tg.create_task(worker(item))

    return results
