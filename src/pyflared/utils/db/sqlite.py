from typing import Any
from sqlalchemy import inspect
from sqlalchemy.dialects.sqlite import insert, Insert
from sqlalchemy.sql.elements import KeyedColumnElement
from sqlmodel import SQLModel


def _build_base_sqlite_insert(
        *values: SQLModel
) -> tuple[Insert, list[str], dict[str, KeyedColumnElement[Any]]]:
    """
    Core helper that validates inputs, builds the base SQLite INSERT statement,
    extracts primary key names, and maps the columns available for update.
    """
    if not values:
        raise ValueError("No instances provided to insert/upsert.")

    model_class: type[SQLModel] = type(values[0])
    mapper = inspect(model_class)

    # 1. Prepare data batch
    data = [obj.model_dump() for obj in values]

    # 2. Build the base INSERT
    stmt = insert(model_class).values(data)

    # 3. Identify Primary Keys
    pk_names = [c.name for c in mapper.primary_key]

    if not pk_names:
        raise ValueError(
            f"No primary key found for model {model_class.__name__}. "
            "SQLite conflict resolution requires a primary key constraint."
        )

    # 4. Build update map
    # Extracting dictionary keys from the first object ensures we only
    # attempt to update columns that were actually provided in the dump.
    provided_keys = data[0].keys()

    # Create a dictionary of columns that should be updated on conflict.
    # We use stmt.excluded to reference the incoming data that was rejected.
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in mapper.columns
        if not c.primary_key and c.name in provided_keys
    }

    return stmt, pk_names, update_cols


def sqlite_insert_or_do_nothing_statement(*values: SQLModel) -> Insert:
    """
    Builds an SQLite INSERT statement that silently ignores rows if their
    primary key already exists.
    """
    stmt, pk_names, _ = _build_base_sqlite_insert(*values)

    return stmt.on_conflict_do_nothing(index_elements=pk_names)


def sqlite_insert_or_update_statement(*values: SQLModel) -> Insert:
    """
    Builds an SQLite INSERT statement that updates existing rows if their
    primary key already exists (Upsert).
    """
    stmt, pk_names, update_cols = _build_base_sqlite_insert(*values)

    # If all columns are PKs (e.g. pure Link Tables with no extra data),
    # an update makes no sense. Fall back to DO NOTHING.
    if not update_cols:
        return stmt.on_conflict_do_nothing(index_elements=pk_names)

    return stmt.on_conflict_do_update(
        index_elements=pk_names,
        set_=update_cols
    )
