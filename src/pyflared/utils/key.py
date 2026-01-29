import asyncio

import keyring


# run the blocking keyring call in a separate thread so main event loop stays responsive.

async def get_secret(service: str, username: str) -> str | None:
    return await asyncio.to_thread(keyring.get_password, service, username)


async def put_secret(service: str, username: str, password: str) -> None:
    return await asyncio.to_thread(keyring.set_password, service, username, password)


async def delete_secret(service: str, username: str) -> None:
    return await asyncio.to_thread(keyring.delete_password, service, username)
