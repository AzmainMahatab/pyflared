import asyncio

import typer

import pyflared
from .ssh import ssh_manager
from .token import token_manager
from .tunnel import tunnel_manager

app = typer.Typer(help="Pyflared, a tool that helps auto configuring cloudflared tunnels")

app.add_typer(tunnel_manager, name="tunnel")
app.add_typer(ssh_manager, name="ssh")
app.add_typer(token_manager, name="token")


@app.command()
def version():
    """Show version info."""
    v: str = asyncio.run(pyflared.binary_version())
    typer.echo(v)

# @app.command()
# def binary():
#     x = pyflared._commands.binary_path()
#     typer.echo(x)
