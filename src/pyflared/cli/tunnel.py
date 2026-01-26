import asyncio
import logging
import sys

import pyflared
import typer
from pydantic import SecretStr
from pyflared import _patterns
from pyflared.api_sdk.parse import Mapping
from pyflared.api_sdk.tunnel_manager import TunnelManager
from pyflared.cli.common import err_console
from pyflared.log.config import isolated_logging
from pyflared.shared.types import OutputChannel
from rich.panel import Panel

tunnel_subcommand = typer.Typer(help="Use for creating quick tunnels and dns mapped tunnel")


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
    tunnel_process = pyflared.run_quick_tunnel(service)  # TODO: Fix it! we cannot run in bg and end
    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        asyncio.run(tunnel_process.start_background([print_tunnel_box]))


async def remove_orphans(
        api_token: SecretStr
):
    tunnel_manager = TunnelManager(api_token.get_secret_value())
    await tunnel_manager.remove_orphans()
    await tunnel_manager.client.close()


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


def pretty_tunnel_status(line: bytes, _: OutputChannel):
    if _patterns.starting_tunnel in line:
        err_console.print("Starting Tunnel...")
    elif b"ERR" in line:
        err_console.print(f"[bold red]{line.decode()}[/bold red]")
    # TODO: Add other Index check
    # TODO: Add connection config
    elif _patterns.all_tunnels_connected in line:
        # err_console.print(line)
        err_console.print(
            "[green]Tunnel status is healthy, with all 4 connections[/green]")  # TODO: Add locations and protocols


@tunnel_subcommand.command("mapped")
def mapped_tunnel(
        pair_args: list[str] = typer.Argument(
            metavar="DOMAIN=SERVICE",  # Changes display in usage synopsis
            help="List of mappings in the format 'domain=service?verify=<true|false|domain.com>'",
        ),
        keep_orphans: bool = typer.Option(
            False,
            "--keep-orphans",
            "-k",
            help="Preserve orphan tunnels (prevents default removal)."
        ),
        tunnel_name: str | None = typer.Option(
            None, "--tunnel-name", "-n",
            help="Tunnel name",
            show_default="hostname_YYYY-MM-DD_UTC..."
        ),
        api_token: SecretStr | None = typer.Option(
            None,
            envvar="CLOUDFLARE_API_TOKEN",
            parser=SecretStr,
            help="Cloudflare API Token to manage tunnels and dns",  # TODO: specify token needed permission
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full cloudflared logs")
):
    """
        Establish mapped tunnels for one or multiple services.
        You can pass multiple pairs separated by spaces.

        Example:
          $ pyflared tunnel mapped example.com=localhost:8000 example2.com=http://localhost:1234 example3.com=https://localhost:1234 example4.com=1234
    """

    if not api_token:
        # Securely prompt the user (hide input)
        api_token = SecretStr(typer.prompt("Please enter your CF API token", hide_input=True))

    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        # pair_dict = Mappings(parse_pair(p) for p in pair_args)
        pairs = [Mapping.from_str(p) for p in pair_args]
        tunnel = pyflared.run_dns_fixed_tunnel(
            pairs, api_token=api_token.get_secret_value(), remove_orphan=not keep_orphans,
            tunnel_name=tunnel_name)  # TODO: pass remove_orphan
        asyncio.run(tunnel.start_background([pretty_tunnel_status]))
