from collections.abc import Iterable


def first[T](iterable: Iterable[T]) -> T:
    if x := next(iter(iterable), None):
        return x
    raise ValueError("Iterable is empty")
