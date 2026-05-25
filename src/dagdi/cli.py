"""Main CLI entry point for Dagdi."""

import typer
from typing import Optional

from . import __version__

from .commands.discovery import discovery_app
from .commands.monitoring import top
from .commands.service_management import (
    service_app,
    manage_single_service,
    manage_multiple_services,
    manage_all_services,
)
from .commands.logs import logs
from .commands.ssh import ssh as ssh_command
from .commands.context import context_app
from .commands.config import app as config_app

# Create main app
app = typer.Typer(
    help="Dagdi - Context-aware Linux infrastructure management CLI",
    no_args_is_help=False,
    invoke_without_command=True,
)

# Add command groups
app.add_typer(discovery_app, name="list", help="List infrastructure components")
app.command(name="top", help="Monitor server metrics")(top)
app.add_typer(service_app, name="manage", help="Manage services")
app.command(name="ms", help="Manage single service")(manage_single_service)
app.command(name="mss", help="Manage multiple services")(manage_multiple_services)
app.command(name="mas", help="Manage all services")(manage_all_services)
app.command(name="logs", help="Stream logs from one or more services")(logs)
app.command(name="ssh", help="SSH into a server")(ssh_command)
app.add_typer(context_app, name="context", help="Manage context")
app.add_typer(config_app, name="config", help="Manage configuration")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"dagdi {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
    timeout: Optional[int] = typer.Option(
        None,
        "--timeout",
        help="SSH timeout in seconds (overrides config)"
    ),
    on_failure: Optional[str] = typer.Option(
        None,
        "--on-failure",
        help="Behavior on partial failure: continue|stop|prompt"
    ),
) -> None:
    """
    Dagdi - Context-aware Linux infrastructure management CLI
    
    Dagdi provides a unified interface for managing distributed infrastructure.
    It uses YAML configuration files to define your infrastructure topology
    and supports context-based operations for easier management.
    
    Examples:
        dagdi config generate              # Generate template configuration
        dagdi config validate              # Validate configuration
        dagdi context set -p app -e prod   # Set context
        dagdi list products                # List all products
        dagdi list environments -p app     # List environments for product
        dagdi top                          # Show server metrics
        dagdi manage service nginx status  # Check service status
        dagdi logs nginx                   # Stream service logs
        dagdi logs nginx api               # Stream multiple service logs
        dagdi ssh                          # SSH into a server
    
    For more information, visit: https://github.com/thetechworms/dagdi
    """
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Store global options in context for use by subcommands
    if ctx.obj is None:
        ctx.obj = {}
    
    if timeout is not None:
        ctx.obj["timeout"] = timeout
    
    if on_failure is not None:
        ctx.obj["on_failure"] = on_failure


def cli() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli()
