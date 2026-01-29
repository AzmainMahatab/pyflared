from collections.abc import Sequence, Iterable
from typing import Callable, NamedTuple

from pyflared.shared.types import AwaitableMaybe
from pyflared.utils.asyncio.wait import safe_awaiter


# 1. Structures


# 2. Callback Types


# The Combined Hook:
# 'winner' is T if successful, or None if completely exhausted.
# type FailedAttempts[T] = Sequence[FailedAttempt[T]]

class FailedAttempt[T](NamedTuple):
    item: T
    error: Exception


class Completion[T](NamedTuple):
    success_item: T
    # failures: FailedAttempts[T]
    failures: Sequence[FailedAttempt[T]]


type AsyncOnEachFail[T] = Callable[[FailedAttempt[T]], AwaitableMaybe[None]]
type AsyncOnComplete[T] = Callable[[Completion[T]], AwaitableMaybe[None]]

type Attempts[T] = AwaitableMaybe[Iterable[T]]


async def run_failover[T, R](
        func: Callable[[T], AwaitableMaybe[R]],
        items: Attempts[T],
        *,
        on_each_fail: AsyncOnEachFail[T] | None = None,
        on_complete: AsyncOnComplete[T] | None = None,
) -> R:
    """
    Executes 'await func(item)' for each item until success.
    - on_fail: Triggered immediately on individual errors.
    - on_complete: Triggered exactly ONCE at the very end of the execution, 
                   providing the winner (if any) and all failures.
    """
    failures: list[FailedAttempt[T]] = []
    items = await safe_awaiter(items)

    if not items:
        raise ValueError("No items provided.")

    for item in items:
        try:
            result = await safe_awaiter(func(item))

            # SUCCESS PATH
            if on_complete:
                # Pass the winning item and the history of failures
                await safe_awaiter(on_complete(Completion(item, failures)))

            return result

        except Exception as e:
            # FAILURE PATH
            attempt = FailedAttempt(item, e)
            failures.append(attempt)

            if on_each_fail:
                await safe_awaiter(on_each_fail(attempt))

    # Raise ExceptionGroup (Python 3.11+) All failed!
    raise ExceptionGroup(
        f"All {len(failures)} attempts failed",
        [f.error for f in failures]
    )
