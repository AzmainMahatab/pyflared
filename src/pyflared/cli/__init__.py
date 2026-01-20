import asyncio

import pyflared
import typer
from .ssh import ssh_subcommand
from .tunnel import tunnel_subcommand

app = typer.Typer(help="Pyflared, a tool that helps auto configuring cloudflared tunnels")

app.add_typer(tunnel_subcommand, name="tunnel")  # tool tunnel
app.add_typer(ssh_subcommand, name="ssh")  # ssh tool


@app.command()
def version():
    """Show version info."""
    v: str = asyncio.run(pyflared.binary_version())
    typer.echo(v)

# @app.command()
# def binary():
#     x = pyflared._commands.binary_path()
#     typer.echo(x)
