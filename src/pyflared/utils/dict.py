from typing import Any


def remove_key[T](my_dict: dict[T, Any], key: T) -> bool:
    """Check if a key was deleted from a dictionary using pop method."""
    return my_dict.pop(key, None) is not None
