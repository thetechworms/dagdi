"""Interactive SSH connection command for Dagdi CLI."""

import os
import shutil
import subprocess
import sys
from typing import List, Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from dagdi.config.loader import load_all_configurations
from dagdi.config.merger import merge_configurations
from dagdi.config.validator import validate_configuration
from dagdi.config.resolver import resolve_services
from dagdi.context.manager import get_context
from dagdi.models import Server
from dagdi.output.themes import get_theme, styled
from dagdi.resolver import resolve_scope


console = Console()


def _find_ssh_binary() -> str:
    """Locate the native ssh binary on the system."""
    path = shutil.which("ssh") or shutil.which("ssh.exe")
    if not path:
        raise RuntimeError(
            "Could not find 'ssh' binary on your system.\n"
            "Please install OpenSSH or ensure it is on your PATH."
        )
    return path


def _build_ssh_args(ssh_binary: str, server: Server, ip: str) -> List[str]:
    """Build the argument list for the native ssh command."""
    args = [ssh_binary]

    if server.ssh_config.key_path:
        key_path = os.path.expanduser(server.ssh_config.key_path)
        args.extend(["-i", key_path])

    if server.ssh_config.port != 22:
        args.extend(["-p", str(server.ssh_config.port)])

    args.extend(["-o", "StrictHostKeyChecking=no"])

    args.append(f"{server.ssh_config.username}@{ip}")
    return args


def _display_server_table(servers: List[Server]) -> None:
    """Display a Rich table of servers for selection."""
    t = get_theme()
    table = Table(
        title="Available Servers",
        box=box.ROUNDED,
        show_lines=True,
        title_style=t.title,
    )
    table.add_column("#", style=t.number, justify="right", width=4)
    table.add_column("Server", style=t.bold)
    table.add_column("IP(s)", style=t.col_server)
    table.add_column("Services", style=t.col_service)

    for idx, server in enumerate(servers, 1):
        ips = ", ".join(server.ips)
        services = ", ".join(
            s.friendly_name or s.name for s in server.services
        ) or "-"
        table.add_row(str(idx), server.name, ips, services)

    console.print()
    console.print(table)


def _prompt_server_selection(servers: List[Server]) -> Server:
    """Show server table and prompt user to pick one."""
    _display_server_table(servers)
    console.print()

    while True:
        choice = typer.prompt(f"Select server [1-{len(servers)}]", type=int)
        if 1 <= choice <= len(servers):
            return servers[choice - 1]
        console.print(
            styled(
                f"Invalid choice. Please enter a number between 1 and {len(servers)}.",
                "error_text",
            )
        )


def _prompt_ip_selection(server: Server) -> str:
    """If the server has multiple IPs, prompt which one to use."""
    if len(server.ips) == 1:
        return server.ips[0]

    console.print(
        f"\n{styled('Server', 'bold')} {styled(server.name, 'highlight')} "
        f"{styled('has multiple IPs:', 'bold')}"
    )
    for idx, ip in enumerate(server.ips, 1):
        console.print(f"  {styled(str(idx), 'username')}. {ip}")
    console.print()

    while True:
        choice = typer.prompt(f"Select IP [1-{len(server.ips)}]", type=int)
        if 1 <= choice <= len(server.ips):
            return server.ips[choice - 1]
        console.print(
            styled(
                f"Invalid choice. Please enter a number between 1 and "
                f"{len(server.ips)}.",
                "error_text",
            )
        )


def _exec_ssh(args: List[str]) -> None:
    """Replace the current process with the ssh binary."""
    if sys.platform == "win32":
        proc = subprocess.run(args)
        raise typer.Exit(proc.returncode)
    else:
        os.execvp(args[0], args)


def ssh(
    product: Optional[str] = typer.Option(
        None, "-p", "--product", help="Product name"
    ),
    environment: Optional[str] = typer.Option(
        None, "-e", "--environment", help="Environment name"
    ),
    server: Optional[str] = typer.Option(
        None, "--server", help="Connect to a specific server by name"
    ),
    ip: Optional[str] = typer.Option(
        None, "--ip", help="Connect to a specific IP address"
    ),
) -> None:
    """SSH into a server.

    Resolves connection details from your configuration and context,
    presents an interactive server picker when needed, and hands off
    to the native ssh binary.

    Examples:
        dagdi ssh                           # Pick from servers in current context
        dagdi ssh -p app -e prod            # Pick from servers in app/prod
        dagdi ssh --server web-1            # Connect directly to web-1
        dagdi ssh --ip 10.0.1.10            # Connect directly to IP
    """
    try:
        ssh_binary = _find_ssh_binary()

        yaml_configs = load_all_configurations()
        merged_config = merge_configurations(yaml_configs)
        config = validate_configuration(merged_config)
        config = resolve_services(config)

        current_context = get_context()

        scope = resolve_scope(
            config=config,
            product=product or (
                current_context.get("product") if current_context else None
            ),
            environment=environment or (
                current_context.get("environment") if current_context else None
            ),
            server=server,
            ip=ip,
        )

        if not scope.servers:
            typer.echo("No servers found matching the specified scope.")
            raise typer.Exit(1)

        if len(scope.servers) == 1:
            target_server = scope.servers[0]
        else:
            console.print(
                f"{styled('Servers in', 'bold')} {styled(scope.product, 'highlight')} / "
                f"{styled(scope.environment, 'highlight')}:"
            )
            target_server = _prompt_server_selection(scope.servers)

        target_ip = _prompt_ip_selection(target_server)

        args = _build_ssh_args(ssh_binary, target_server, target_ip)

        port_info = ""
        if target_server.ssh_config.port != 22:
            port_info = f" (port {target_server.ssh_config.port})"

        console.print(
            f"\n{styled('Connecting to', 'success')} "
            f"{styled(target_server.name, 'highlight')} "
            f"({target_ip}){port_info} "
            f"as {styled(target_server.ssh_config.username, 'username')}...\n"
        )

        _exec_ssh(args)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
