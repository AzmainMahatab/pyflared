from pyflared import cloudflared


def test_binary() -> str | None:
    version = cloudflared.version()
    print(version)
    assert version
