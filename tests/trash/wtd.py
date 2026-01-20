from typing import Annotated

import typer
from pydantic import SecretStr

app = typer.Typer()


@app.command()
def connect(
        # 1. Accept a plain string
        api_key_raw: Annotated[
            str | None,
            typer.Option(
                None,
                "--api-key",  # Map flag name explicitly
                envvar="CLOUDFLARE_API_TOKEN",
                help="CF API Token",
            )
        ] = None
):
    # 2. Convert manually
    api_key: SecretStr | None = SecretStr(api_key_raw) if api_key_raw else None

    if api_key:
        print(f"Token: {api_key.get_secret_value()}")


# @app.command()
# def test2(test_list: Annotated[list[int], typer.Option()] = [1, 2, 3, 4]) -> None:
#     print(test_list)


if __name__ == "__main__":
    app(args=["--help"])
