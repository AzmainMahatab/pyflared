from collections.abc import AsyncIterable, Callable, AsyncIterator

from pyflared.shared.types import AwaitableMaybe
from pyflared.utils.asyncio.wait import safe_awaiter


async def async_transformer[T, R](async_iterable: AsyncIterable[T], func: Callable[[T], AwaitableMaybe[R]]) -> \
AsyncIterator[R]:
    async for i in async_iterable:
        yield await safe_awaiter(func(i))
