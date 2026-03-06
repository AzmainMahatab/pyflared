from typing import Self
from cloudflare.types.zones import Zone
from sqlmodel import Field

from pyflared.utils.db.sqlmodel import SQLModelBase


class Token(SQLModelBase, table=True):
    value: str = Field(primary_key=True, min_length=40, max_length=40)
    # value: SecretStr = Field(primary_key=True, min_length=40, max_length=40)
    name: str = Field(unique=True)

    @property
    def masked_rep(self) -> str:
        masked = self.value[:4] + "..."
        return f"{self.name}: {masked}"


class TokenLookupLink(SQLModelBase, table=True):
    token_value: str = Field(primary_key=True,
                             foreign_key=f"{Token.__tablename__}.value",
                             index=True,
                             ondelete="CASCADE")

    search_key: str = Field(primary_key=True, index=True, )  # this can be both zone_name or account_id


class ZoneEntry(SQLModelBase, table=True):
    name: str = Field(primary_key=True)

    id: str = Field(unique=True)
    account_id: str = Field(index=True)

    @classmethod
    def from_response(cls, zone: Zone) -> Self:
        return cls(name=zone.name, id=zone.id,
                   account_id=zone.account.id)  # pyright: ignore[reportArgumentType]


cache_tables = (ZoneEntry, TokenLookupLink)
