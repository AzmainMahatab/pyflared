import asyncio
import logging
import sys

import typer
from rich.panel import Panel
from typing_extensions import Annotated

import pyflared
from pyflared import cleanup
from pyflared.shared import _patterns
from pyflared.api_sdk.parse import Mapping
from pyflared.log.config import isolated_logging
from pyflared.shared.console import err_console
from pyflared.shared.types import OutputChannel

tunnel_manager = typer.Typer(help="Use for creating quick tunnels and dns mapped tunnel")


def display_tunnel_info(url: str) -> None:
    """
    Displays the tunnel URL in a high-visibility panel.
    """
    # [link=...] makes it clickable in supported terminals
    # [bold green] styles the text
    content = (
            f"[bold green]Tunnel Created Successfully![/bold green]\n\n"
            + f"Your URL is: [link={url}]{url}[/link]"
    )

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


@tunnel_manager.command("quick")
def quick_tunnel(
        service: str,
        verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show full cloudflared logs")] = False
):
    """
        Cloudflared QuickTunnels without domains.
        Example:
            $ pyflared tunnel quick example.com=localhost:8000 example2.com=localhost:1234
    """
    tunnel_process = pyflared.run_quick_tunnel(service)  # TODO: Fix it! we cannot run in bg and end
    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        _ = asyncio.run(tunnel_process.start_background([print_tunnel_box]))


@tunnel_manager.command("cleanup")
def cleanup_tunnels_n_dns(
        all_resources: Annotated[bool, typer.Option("--all", "-a", help="Delete ALL tunnels and DNS records, not just orphans")] = False,
        force: Annotated[bool, typer.Option("--force", "-f", help="Bypass confirmation prompt when deleting all resources")] = False,
        verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show full cloudflared logs")] = False,
) -> None:
    """
    Clean up tunnels and DNS records.

    By default, only removes orphaned resources: unnamed (ephemeral) tunnels
    that are inactive and their associated DNS records.

    Use --all to delete ALL tunnels and DNS records, including named and active
    ones. This is a destructive action and requires --force to skip the
    confirmation prompt.
    """
    # Protect the destructive --all action with a confirmation prompt
    if all_resources and not force:
        _ = typer.confirm(
            "WARNING: You are about to delete ALL tunnels and DNS records, including active and named ones. Are you sure?",
            abort=True
        )

    # Set the logging context and execute the async cleanup,
    # passing the boolean so the backend knows the intended scope.
    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        asyncio.run(cleanup(all_resources))


def pretty_tunnel_status(line: bytes, _: OutputChannel):
    if _patterns.starting_tunnel in line:
        err_console.print("Starting Tunnel...")
    # line.startswith(b"ERR")
    elif b"ERR" in line:
        err_console.print(f"[bold red]{line.decode()}[/bold red]")
    # TODO: Add other Index check
    # TODO: Add connection config
    elif _patterns.all_tunnels_connected in line:
        # err_console.print(line)
        err_console.print(
            "[green]Tunnel status is healthy, with all 4 connections[/green]")  # TODO: Add locations and protocols


@tunnel_manager.command("mapped")
def mapped_tunnel(
        pair_args: Annotated[list[str], typer.Argument(
            metavar="DOMAIN=SERVICE",  # Changes display in usage synopsis
            help="List of mappings in the format 'domain=service?verify=<true|false|domain.com>'",
        )],
        tunnel_name: Annotated[str | None, typer.Option(
            "--tunnel-name", "-n",
            help="Tunnel name",
            show_default="hostname_YYYY-MM-DD_UTC..."
        )] = None,
        force: Annotated[
            bool, typer.Option("--force", "-f", help="Take over dns from other tunnels even if named")] = False,
        verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show full cloudflared logs")] = False,
):
    """
    Establish mapped tunnels for one or multiple services.

    Without --tunnel-name the tunnel is ephemeral: it is created fresh and both
    the tunnel and its DNS records are automatically cleaned up on shutdown
    (Ctrl+C).

    With --tunnel-name the tunnel is persistent: it is reused across runs and
    its DNS records are preserved on shutdown. Named tunnels also guard their
    DNS records against takeover by other tunnel setups — use --force to
    override this protection.

    Mapping format (DOMAIN=SERVICE):
      Port only:        app.com=8000
      Host:port:        app.com=localhost:3000
      Explicit scheme:  app.com=https://backend:443
      Path routing:     app.com/api=localhost:8000  or  api.com=8000/v1/api
      Unix socket:      sock.com=/var/run/app.sock
      TLS control:      app.com=https://backend?verify_tls=false|true|custom.com
      TCP (auto):       db.com=5432  (PostgreSQL, Redis, etc. → tcp://)
      SSH (auto):       ssh.com=22   (→ ssh://)
      Special:          test.com=hello_world | http_status:404 | bastion

    Example:
      $ pyflared tunnel mapped example.com=localhost:8000 example2.com=http://localhost:1234
    """

    with isolated_logging(logging.DEBUG if verbose else logging.INFO):
        # pair_dict = Mappings(parse_pair(p) for p in pair_args)
        pairs = [Mapping.from_str(p) for p in pair_args]
        # if not api_token:
        #     # Securely prompt the user (hide input)
        #     api_token = SecretStr(typer.prompt("Please enter CLOUDFLARE_API_TOKEN", hide_input=True))

        tunnel_process = pyflared.run_dns_fixed_tunnel(
            pairs,
            tunnel_name=tunnel_name,
            force=force,
        )

        _ = asyncio.run(tunnel_process.start_background([pretty_tunnel_status]))
