from typing import dataclass_transform

from sqlmodel import Field
from sqlmodel.main import FieldInfo, SQLModel


@dataclass_transform(kw_only_default=True, field_specifiers=(Field, FieldInfo))
class SQLModelBase(SQLModel):
    """All our database tables will inherit from this instead of SQLModel directly."""
    pass
