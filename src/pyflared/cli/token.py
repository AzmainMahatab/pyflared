import asyncio

import typer
from typing_extensions import Annotated

from pyflared.core.model import Token
from pyflared.core.repository import token_list, add_token, remove_tokens, nuke_tokens

token_manager = typer.Typer(help="Use for managing CLOUDFLARE_API_TOKEN")


@token_manager.command(name="ls", hidden=True)
@token_manager.command(name="list")
def list_tokens() -> None:
    """
    List all CLOUDFLARE_API_TOKEN.

    (Alias: ls)
    """

    tokens = asyncio.run(token_list())
    if not tokens:
        typer.echo("No keys found!")
        return
    for token in tokens:
        typer.echo(token.masked_rep)


@token_manager.command()
def add(
        name: Annotated[str, typer.Argument(help="Friendly name for this token (e.g. 'zone-a')")],
        token: Annotated[
            str, typer.Option(prompt=True, hide_input=True, help="CLOUDFLARE_API_TOKEN to manage tunnels and dns")],
) -> None:
    """
    Add CLOUDFLARE_API_TOKEN to manage tunnels and dns
    """
    token2 = Token(value=token, name=name)
    if asyncio.run(add_token(token2)):
        typer.echo(f"Token added!")
    else:
        typer.echo(f"Token add Failed!")


@token_manager.command(name="rm", hidden=True)
@token_manager.command()
def remove(
        name: Annotated[str, typer.Argument(..., help="Remove a token by name")],
) -> None:
    """
    Remove a CLOUDFLARE_API_TOKEN from the pool by its friendly name.

    (Alias: rm)
    """
    if asyncio.run(remove_tokens(name)):
        typer.echo(f"Token '{name}' removed!")
    else:
        typer.secho(f"Token '{name}' not found in pool!", fg=typer.colors.YELLOW)


@token_manager.command()
def nuke() -> None:
    """
    Nuke the token pool, removing all tokens.
    """
    asyncio.run(nuke_tokens())
    typer.echo(f"Token pool nuked!")
