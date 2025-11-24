from pyflared import cloudflared


def test_binary() -> str | None:
    v = binary.version()
    print(v)
    assert v
