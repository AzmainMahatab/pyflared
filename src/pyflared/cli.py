import asyncio
import logging
import sys

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.panel import Panel

import pyflared.cloudflared
from pyflared.log.config2 import isolated_logging
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

def output_result(url: str) -> None:
    if sys.stdout.isatty():
        # If a human is watching, show the pretty panel
        display_tunnel_info(url)
    else:
        # If the user is piping output (e.g., > file.txt), just print the raw URL
        print(url)


@app.command()
def version():
    """Show version info."""
    v = asyncio.run(pyflared.cloudflared.version())
    typer.echo(v)

    # typer.Exit(code=1)


console = Console()


def display_tunnel_info(url: str) -> None:
    """
    Displays the tunnel URL in a high-visibility panel.
    """
    # [link=...] makes it clickable in supported terminals
    # [bold green] styles the text
    content = f"[bold green]Tunnel Created Successfully![/bold green]\n\n" \
              f"Your URL is: [link={url}]{url}[/link]"

    panel = Panel(
        content,
        title="[bold blue]Cloudflared Tunnel[/bold blue]",
        border_style="green",
        expand=False,  # Fits the panel to the content width, not full screen
        padding=(1, 2)  # Add some breathing room inside the box
    )

    console.print(panel)


@tunnels_app.command("quick")
def quick_tunnel(
        service: str,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs")
):
    """Cloudflared QuickTunnels without domains."""
    tunnel_process = pyflared.cloudflared.run_quick_tunnel(service)  # TODO: Fix it! we cannot run in bg and end
    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        asyncio.run(tunnel_process.start_background([print_tunnel_box]))


def parse_pair(value: str) -> tuple[str, str]:
    # --- Validator ---
    if "=" not in value:
        raise typer.BadParameter(f"Format must be 'domain=service', got: {value}")
    domain, service = value.split("=", 1)
    return domain, service.rstrip("/")  # TODO: support more cleanings


def print_all(line: bytes, c: OutputChannel):
    # print(b.decode(), end="")
    print(line.decode())


def print_tunnel_box(line: bytes, _: OutputChannel):
    output_result(line.decode().strip())


@tunnels_app.command("mapped")
def mapped_tunnel(
        pair_args: list[str],
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs"),
        api_token: SecretStr | None = typer.Option(
            None,
            envvar="CLOUDFLARE_API_TOKEN",
            parser=SecretStr,
            help="Your secret API key.",  # Todo: specify token needed permission
        )
):
    """Bind domains to services using domain=service format."""
    if not api_token:
        # Securely prompt the user (hide input)
        api_token = typer.prompt("Please enter your API Key", hide_input=True)

    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        pair_dict = Mappings(parse_pair(p) for p in pair_args)
        tunnel = pyflared.cloudflared.run_dns_fixed_tunnel(pair_dict, api_token)  # TODO: pass remove_orphan
        asyncio.run(tunnel.start_background([print_all]))
