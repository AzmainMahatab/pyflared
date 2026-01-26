import pyflared


async def test_binary_version() -> str | None:
    version = await pyflared.binary_version()
    assert "version" in version, f"Cloudflared version: {version}"


async def test_binary_path() -> str | None:
    path = pyflared.binary_path()
    assert "cloudflared" in str(path), f"Cloudflared binary_path: {path}"
