import pyflared


async def test_binary() -> str | None:
    version = await pyflared.binary_version()
    assert "version" in version, f"Cloudflared version: {version}"
