from beartype.door import is_bearable
from typing_extensions import TypeIs, TypeForm


def is_of_type[T](val: object, hint: TypeForm[T]) -> TypeIs[T]:
    """
    A unified, typesafe runtime guard that works for ANY type or alias.

    val: The unknown runtime object you want to check.
    hint: The type expression (class, alias, or union) that defines T.
    """
    # We still need the ignore comment here because beartype's internal
    # signature hasn't fully updated to natively accept TypeForm yet.
    return is_bearable(val, hint)  # pyright: ignore[reportArgumentType]
