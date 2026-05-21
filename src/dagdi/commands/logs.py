"""Log streaming commands for Dagdi CLI."""

import sys
from typing import Optional
import typer
from rich.console import Console

from dagdi.config.loader import load_all_configurations
from dagdi.config.merger import merge_configurations
from dagdi.config.validator import validate_configuration
from dagdi.config.resolver import resolve_services
from dagdi.context.manager import get_context
from dagdi.output.formatter import highlight_log_line
from dagdi.resolver import resolve_scope, get_target_ips
from dagdi.ssh.executor import execute_command_stream


class _HighlightingWriter:
    """Wraps sys.stdout to apply log-level highlighting to each line."""

    def __init__(self, console: Console):
        self._console = console
        self._buffer = ""

    def write(self, data: str) -> int:
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            highlighted = highlight_log_line(line)
            self._console.print(highlighted, highlight=False)
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            highlighted = highlight_log_line(self._buffer)
            self._console.print(highlighted, end="", highlight=False)
            self._buffer = ""

logs_app = typer.Typer(help="Log streaming commands")


def _build_log_command(
    service_obj,
    use_sudo: bool = False,
) -> str:
    """
    Build a log streaming command for a service.
    
    Args:
        service_obj: Service object
        use_sudo: Whether to use sudo
    Returns:
        Command string to stream logs
    """
    service_type = service_obj.type
    service_name = service_obj.name

    # Allow explicit per-service override for all service types.
    log_command = service_obj.config.get("log_command")
    if log_command:
        cmd = log_command
    
    elif service_type == "systemd":
        cmd = f"journalctl -u {service_name} -f"
    elif service_type == "docker":
        container_name = service_obj.config.get("container_name", service_name)
        cmd = f"docker logs -f {container_name}"
    else:
        raise ValueError(f"Unknown service type: {service_type}")
    
    if use_sudo:
        cmd = f"sudo {cmd}"
    
    return cmd


@logs_app.command()
def logs(
    service_name: str = typer.Argument(..., help="Service name"),
    product: Optional[str] = typer.Option(
        None, "-p", "--product", help="Product name"
    ),
    environment: Optional[str] = typer.Option(
        None, "-e", "--environment", help="Environment name"
    ),
    server: Optional[str] = typer.Option(
        None, "--server", help="Filter by server name"
    ),
    ip: Optional[str] = typer.Option(None, "--ip", help="Filter by IP address"),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", help="SSH timeout in seconds"
    ),
) -> None:
    """Stream logs from a service.

    Examples:
        dagdi logs nginx                    # Stream logs from nginx
        dagdi logs nginx -p app -e prod     # With product and environment
        dagdi logs nginx --server web-1     # From specific server
        dagdi logs nginx --ip 10.0.1.10     # From specific IP
    """
    try:
        # Load configuration
        yaml_configs = load_all_configurations()
        merged_config = merge_configurations(yaml_configs)
        config = validate_configuration(merged_config)
        config = resolve_services(config)

        # Load context
        current_context = get_context()

        # Resolve scope with service name
        scope = resolve_scope(
            config=config,
            product=product or (current_context.get("product") if current_context else None),
            environment=environment or (current_context.get("environment") if current_context else None),
            server=server,
            ip=ip,
            service=service_name,
        )

        # Get target servers and IPs
        target_ips = get_target_ips(scope.servers)

        if not target_ips:
            typer.echo("No servers found matching the specified scope.")
            raise typer.Exit(1)

        # If multiple targets, stream from first one
        if len(target_ips) > 1:
            typer.echo(
                f"⚠️  Multiple targets found. Streaming from first target: {target_ips[0][0].name} ({target_ips[0][1]})"
            )

        server_obj, server_ip = target_ips[0]

        # Find the service on this server
        service_obj = next(
            (s for s in server_obj.services if s.name == service_name),
            None
        )
        
        if not service_obj:
            typer.echo(f"Error: Service '{service_name}' not found on server {server_obj.name}")
            raise typer.Exit(1)

        # Build log command
        ssh_username = (server_obj.ssh_config.username or "").strip().lower()
        should_use_sudo = server_obj.ssh_config.sudo and ssh_username != "root"

        cmd = _build_log_command(
            service_obj,
            use_sudo=should_use_sudo,
        )

        # Stream logs
        typer.echo(f"Streaming logs from {server_obj.name} ({server_ip})...")
        typer.echo("Press Ctrl+C to stop.\n")

        original_stdout = sys.stdout
        log_console = Console(file=original_stdout, highlight=False)
        sys.stdout = _HighlightingWriter(log_console)  # type: ignore[assignment]
        try:
            execute_command_stream(server_obj, server_ip, cmd, timeout=timeout)
        except KeyboardInterrupt:
            pass
        finally:
            sys.stdout = original_stdout
            typer.echo("\n\nLog streaming stopped.")

    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
