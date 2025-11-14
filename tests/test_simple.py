from pyflared import binary


def test_binary() -> str | None:
    v = binary.version()
    print(f"\n[Version] {v}")
    assert v, "Version should not be empty"
