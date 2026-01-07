import asyncio
import logging

import typer

import pyflared.cloudflared
from pyflared.log.config import contextual_logger
from pyflared.shared.types import Mappings, OutputChannel

app = typer.Typer(help="MyCLI Tool")
tunnels_app = typer.Typer(help="Manage tunnels")
app.add_typer(tunnels_app, name="tunnel")  # tool tunnel


# def fx(record: logging.LogRecord):
#     return True
#
#
# def fx2(record: int):
#     return True


# console_handler.addFilter(fx2)
# cl = ContextualLogger(console_handler)


@app.command()
def version():
    """Show version info."""
    v = asyncio.run(pyflared.cloudflared.version())
    typer.echo(v)

    # typer.Exit(code=1)


@tunnels_app.command("quick")
def quick_tunnel(
        service: str,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs")
):
    """Cloudflared QuickTunnels without domains."""
    tunnel_process = pyflared.cloudflared.run_quick_tunnel(service)  # TODO: Fix it! we cannot run in bg and end
    with contextual_logger(logging.DEBUG if verbose else logging.INFO):
        asyncio.run(tunnel_process.start_background([print_all]))


def parse_pair(value: str) -> tuple[str, str]:
    # --- Validator ---
    if "=" not in value:
        raise typer.BadParameter(f"Format must be 'domain=service', got: {value}")
    domain, service = value.split("=", 1)
    return domain, service


def print_all(b: bytes, c: OutputChannel):
    # print(b.decode(), end="")
    print(b.decode())


@tunnels_app.command("mapped")
def mapped_tunnel(
        pair_args: list[str],
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs"),
        api_token: str | None = typer.Option(
            None,
            help="Your secret API key.",  # Todo: specify token needed permission
            envvar="CLOUDFLARE_API_TOKEN"
        )
):
    """Bind domains to services using domain=service format."""
    if not api_token:
        # Securely prompt the user (hide input)
        api_token = typer.prompt("Please enter your API Key", hide_input=True)

    pair_dict = Mappings(parse_pair(p) for p in pair_args)

    tunnel = pyflared.cloudflared.run_dns_fixed_tunnel(pair_dict, api_token)

    with contextual_logger(logging.DEBUG if verbose else logging.INFO):
        asyncio.run(tunnel.start_background([print_all]))
