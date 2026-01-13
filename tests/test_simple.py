from loguru import logger

from pyflared import commands


async def test_binary() -> str | None:
    version = await commands.version()
    # print(version)
    logger.info(f"Cloudflared version: {version}")
    assert "version" in version
