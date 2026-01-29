import datetime
import os
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir
from sqlalchemy import event, delete
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select, col, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from pyflared.core.model import ZoneEntry, Token, TokenLookupLink, cache_tables
from pyflared.shared.consts import CF_API_TOKEN
from pyflared.shared.contants import APP_NAME, AUTHOR
from pyflared.utils.run_failover import Completion
from pyflared.utils.db.sqlite import sqlite_insert_or_update_statement
from pyflared.utils.db.sqlmodel import SQLModelBase


@cache
def sqlite_file_name() -> Path:
    # 1. Get the standard user data directory for the OS
    app_data_dir: Path = Path(user_data_dir(appname=APP_NAME, appauthor=AUTHOR))

    # 2. Ensure the directory exists (this is crucial, as it doesn't exist by default)
    app_data_dir.mkdir(parents=True, exist_ok=True)

    # 3. Return the full path to the database file
    return app_data_dir / "cache.db"


sqlite_url = f"sqlite+aiosqlite:///{sqlite_file_name()}"
engine = create_async_engine(
    sqlite_url,
    echo=False,
    # echo=True,
    connect_args={"check_same_thread": False}
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: sqlite3.Connection, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    _ = cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def gen_second_timestamp() -> str:
    """
    Generates a readable timestamp string up to the second.
    """
    now: datetime.datetime = datetime.datetime.now(datetime.UTC)
    # Format: 2-digit year, month, day _ hour, min, sec
    return now.strftime("%y%m%d_%H%M%S")


def _gen_envar_token_name():
    return CF_API_TOKEN + "_" + gen_second_timestamp()


def envar_token() -> Token | None:
    if (token_value := os.environ.get(CF_API_TOKEN)) is not None:
        return Token(value=token_value, name=_gen_envar_token_name())
    return None


async def token_list() -> Sequence[Token]:
    async with AsyncSession(engine) as session:
        result = await session.exec(select(Token))
        return result.all()


async def add_token(token: Token) -> bool:
    async with AsyncSession(engine) as session:
        smt = sqlite_insert_or_update_statement(token)

        result = await session.exec(smt)
        await session.commit()

    return result.rowcount > 0


async def remove_tokens(*token_values_or_names: str) -> bool:
    async with AsyncSession(engine) as session:
        stmt_delete_tokens = (
            delete(Token)
            .where(
                col(Token.value).in_(token_values_or_names) | col(Token.name).in_(token_values_or_names)
            )
        )
        result = await session.exec(stmt_delete_tokens)
        await session.commit()
        return result.rowcount > 0


async def nuke_tokens():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModelBase.metadata.drop_all)


async def ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def invalidate_cache(session: AsyncSession) -> None:
    for tbl in cache_tables:
        _ = await session.exec(delete(tbl))


async def save_trial(completion_response: Completion[str], key: str):
    success_token = completion_response.success_item
    failures = completion_response.failures

    if failures:
        failed_tokens = [attempt.item for attempt in failures]
        async with AsyncSession(engine) as session:
            delete_statement = delete(TokenLookupLink).where(
                col(TokenLookupLink.token_value).in_(failed_tokens),
                col(TokenLookupLink.search_key) == key
            )
            _ = await session.exec(delete_statement)

            link = TokenLookupLink(token_value=success_token, search_key=key)
            update_smt = sqlite_insert_or_update_statement(link)
            _ = await session.exec(update_smt)

            await session.commit()


type TokenLink = dict[str, set[str]]  # Token -> set(connected keys)
type ZoneDict = dict[str, ZoneEntry]  # Domain -> ZoneEntry


@dataclass
class TokenHint:
    token_links: TokenLink = field(default_factory=dict, init=False)

    async def refresh(self):  # DB sync
        memory_store = self.token_links

        # Ensure tables exist to prevent the "no such table" OperationalError
        await ensure_tables()
        async with AsyncSession(engine) as session:
            statement = (
                select(Token, TokenLookupLink.search_key)  # TODO
                .outerjoin(TokenLookupLink)
            )
            result = await session.exec(statement)
            results = result.all()

        for token, search_key in results:
            if token.value not in memory_store:
                memory_store[token.value] = set()
            if search_key is not None:  # pyright: ignore[reportUnnecessaryComparison]
                memory_store[token.value].add(search_key)

    async def priority_tokens(
            self,
            primary_search_key: str | None = None,
            secondary_search_key: str | None = None,  # Useful when you wanna additionally find by zone name
    ) -> Sequence[str]:
        """
        Step 2: Returns a ranked list of token strings from the in-memory cache.
        """
        token_links = self.token_links
        if not token_links:
            await self.refresh()

        if not primary_search_key and not secondary_search_key:
            return list(token_links.keys())

        def calculate_score(token_value: str) -> int:
            score = 0
            for search_key in token_links[token_value]:
                if search_key == primary_search_key:
                    score += 2
                elif search_key == secondary_search_key:
                    score += 1
            return score

        return sorted(token_links.keys(), key=calculate_score, reverse=True)
