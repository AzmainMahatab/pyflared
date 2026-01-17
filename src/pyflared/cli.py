import asyncio
import logging
import re
import sys

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.panel import Panel

import pyflared._commands
from pyflared import _commands
from pyflared.api_sdk.tunnel_manager import TunnelManager
from pyflared.log.config import isolated_logging
from pyflared.shared.types import Mappings, OutputChannel

err_console = Console(stderr=True)

app = typer.Typer(help="Pyflared, a tool that helps auto configuring cloudflared tunnels")


@app.command()
def version():
    """Show version info."""
    v: str = asyncio.run(pyflared.commands.binary_version())
    typer.echo(v)

    # typer.Exit(code=1)


tunnel_subcommand = typer.Typer(help="Use for creating quick tunnels and dns mapped tunnel")
app.add_typer(tunnel_subcommand, name="tunnel")  # tool tunnel


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

    err_console.print(panel)


def clean_domain(url: str) -> str:
    """
    Removes 'http://' or 'https://' from the start,
    AND removes a trailing '/' from the end.
    """
    # ^https?://  -> Matches http:// or https:// at the START
    # |           -> OR
    # /$          -> Matches a / at the END
    return re.sub(r"^https?://|/$", "", url, flags=re.IGNORECASE)


def normalize_if_local_url(url: str) -> str:
    # 1. Always strip the trailing slash(es) first
    url = url.rstrip("/")

    # 2. Case: "8000" -> "http://localhost:8000"
    # Checks if the entire string is just numbers
    if url.isdigit():
        return f"http://localhost:{url}"

    # 3. Case: "localhost:8000" -> "http://localhost:8000"
    if url.startswith("localhost"):
        return f"http://{url}"

    # 4. Default: Return as is (e.g. already has http://)
    return url


def parse_pair(value: str) -> tuple[str, str]:
    # --- Validator ---
    if "=" not in value:
        raise typer.BadParameter(f"Format must be 'domain=service', got: {value}")
    domain, service = value.split("=", 1)
    return clean_domain(domain), normalize_if_local_url(service)


def print_all(line: bytes, _: OutputChannel):
    err_console.print(line.decode())


def print_tunnel_box(line: bytes, _: OutputChannel):
    already_printed = False  # This is because for Links that are not backed by a service, clicking it emits the same line again each time

    def output_result(url: str) -> None:
        nonlocal already_printed
        if already_printed:
            return
        if sys.stdout.isatty():
            # If a human is watching, show the pretty panel
            display_tunnel_info(url)
        else:
            # If the user is piping output (e.g., > file.txt), just print the raw URL
            err_console.print(url)
            # print(url)
        already_printed = True

    output_result(line.decode().strip())


@tunnel_subcommand.command("quick")
def quick_tunnel(
        service: str,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs")
):
    """
        Cloudflared QuickTunnels without domains.
        Example:
            $ pyflared tunnel quick example.com=localhost:8000 example2.com=localhost:1234
    """
    tunnel_process = pyflared.commands.run_quick_tunnel(service)  # TODO: Fix it! we cannot run in bg and end
    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        asyncio.run(tunnel_process.start_background([print_tunnel_box]))


async def remove_orphans(
        api_token: SecretStr
):
    tunnel_manager = TunnelManager(api_token.get_secret_value())
    await tunnel_manager.remove_orphans()
    tunnel_manager.client.close()


@tunnel_subcommand.command("cleanup")
def cleanup_orphans(
        api_token: SecretStr | None = typer.Option(
            None,
            envvar="CLOUDFLARE_API_TOKEN",
            parser=SecretStr,
            help="CF API Token to manage tunnels and dns",  # TODO: specify token needed permission
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs")
):
    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        if not api_token:
            # Securely prompt the user (hide input)
            api_token = SecretStr(typer.prompt("Please enter your CF API token", hide_input=True))
        asyncio.run(remove_orphans(api_token))


all_tunnels_connected = b"INF Registered tunnel connection connIndex=3"


def pretty_tunnel_status(line: bytes, _: OutputChannel):
    if commands.starting_tunnel in line:
        err_console.print("Starting Tunnel...")
    elif b"ERR" in line:
        err_console.print(f"[bold red]{line.decode()}[/bold red]")
    # TODO: Add other Index check
    # TODO: Add connection config
    elif all_tunnels_connected in line:
        # err_console.print(line)
        err_console.print(
            "[green]Tunnel status is healthy, with all 4 connections[/green]")  # TODO: Add locations and protocols


@tunnel_subcommand.command("mapped")
def mapped_tunnel(
        pair_args: list[str] = typer.Argument(
            ...,
            metavar="DOMAIN=SERVICE",  # Changes display in usage synopsis
            help="List of mappings in the format 'domain=service'.",
            show_default=False
        ),
        remove_orphan: bool = typer.Option(
            True, "--remove-orphans", "-ro", help="Remove orphan tunnels"),
        tunnel_name: str | None = typer.Option(
            None,
            help="Tunnel name",
            show_default="hostname_YYYY-MM-DD_UTC..."
        ),
        api_token: SecretStr | None = typer.Option(
            None,
            envvar="CLOUDFLARE_API_TOKEN",
            parser=SecretStr,
            help="CF API Token to manage tunnels and dns",  # TODO: specify token needed permission
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs")
):
    """
        Establish mapped tunnels for one or multiple services.
        You can pass multiple pairs separated by spaces.

        Example:
          $ pyflared tunnel mapped example.com=localhost:8000 example2.com=localhost:1234
    """

    if not api_token:
        # Securely prompt the user (hide input)
        api_token = SecretStr(typer.prompt("Please enter your CF API token", hide_input=True))

    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        pair_dict = Mappings(parse_pair(p) for p in pair_args)
        tunnel = pyflared.commands.run_dns_fixed_tunnel(
            pair_dict, api_token=api_token.get_secret_value(), remove_orphan=remove_orphan,
            tunnel_name=tunnel_name)  # TODO: pass remove_orphan
        asyncio.run(tunnel.start_background([pretty_tunnel_status]))
