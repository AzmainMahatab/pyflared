def set_remove[T](target_set: set[T], item: T) -> bool:
    """
    Attempts to remove an item from a set.

    Parameters:
    - target_set: The set you want to modify.
    - item: The element you want to check and remove.

    Returns:
    - bool: True if the item was found and removed, False otherwise.
    """
    if item in target_set:
        target_set.remove(item)
        return True
    return False
