from collections.abc import Iterable, AsyncIterable, AsyncIterator, Generator


def first[T](iterable: Iterable[T]) -> T:
    if x := next(iter(iterable), None):
        return x
    raise ValueError("Iterable is empty")


async def or_empty_aterator[T](async_iterator: AsyncIterable[T] | None) -> AsyncIterator[T]:
    if async_iterator is None:
        return
    async for item in async_iterator:
        yield item


def or_empty_iterator[T](async_iterator: Iterable[T] | None) -> Iterable[T]:
    if async_iterator is None:
        return
    for item in async_iterator:
        yield item


def not_none_generator[T](*values: T | None) -> Generator[T, None, None]:
    """
    Generates values from the provided input that are not ``None``.

    This generator function takes a variable number of input values and yields only
    those which are not ``None``, in the order they are provided. It can handle
    inputs of any type that are passed as arguments.

    :param values: Arbitrary number of input values to be checked. Only non-``None``
        values will be yielded.
    :return: A generator object that yields values from the input, excluding any
        ``None`` values.
    """
    for value in values:
        if value is not None:
            yield value
