from pyflared import commands


async def test_binary() -> str | None:
    version = await cloudflared.version()
    print(version)
    assert "version" in version
