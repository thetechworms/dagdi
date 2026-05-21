"""Monitoring commands for Dagdi CLI."""

import time
from typing import Optional, List, Any, Tuple

import typer
from rich import box
from rich.console import Console as RichConsole
from rich.live import Live
from rich.table import Table

_progress_console = RichConsole()

from dagdi.concurrency import parallel_map_ordered
from dagdi.config.loader import load_all_configurations
from dagdi.config.merger import merge_configurations
from dagdi.config.validator import validate_configuration
from dagdi.config.resolver import resolve_services
from dagdi.context.manager import get_context
from dagdi.output.formatter import Formatter, colorize_metric
from dagdi.output.themes import get_theme, styled
from dagdi.resolver import resolve_scope
from dagdi.ssh.metrics_collector import MetricsCollector

monitoring_app = typer.Typer(help="Monitoring commands")


def _result_key(result: dict) -> str:
    """Build a stable key for a metrics row."""
    return f"{result.get('server', '')}|{result.get('ip', '')}"


def _apply_monitor_change_highlights(
    results: List[dict], previous_values: dict
) -> tuple[List[dict], dict]:
    """Highlight changed metric values between refresh cycles."""
    highlighted_results: List[dict] = []
    current_values: dict = {}
    track_fields = ["cpu", "ram", "disk", "net_up", "net_down"]

    for result in results:
        row = dict(result)
        key = _result_key(result)
        snapshot = {field: f"{result.get(field, 0)}" for field in track_fields}
        current_values[key] = snapshot
        prev_snapshot = previous_values.get(key)

        if prev_snapshot:
            t = get_theme()
            for field in track_fields:
                old = prev_snapshot.get(field, "")
                new = snapshot[field]
                if new != old:
                    if field in {"cpu", "ram", "disk"}:
                        val = f"{result.get(field, 0):.1f}"
                    else:
                        val = f"{result.get(field, 0):.2f}"
                    row[field] = styled(val, "metric_changed")

        highlighted_results.append(row)

    return highlighted_results, current_values


def _format_metric_value(value: Any, precision: int, color: bool = False) -> str:
    """Format numeric metrics or pass through styled strings."""
    if isinstance(value, str):
        return value
    if color:
        return colorize_metric(value, fmt=f".{precision}f")
    return f"{value:.{precision}f}"


def _interruptible_sleep(seconds: float, interval: float = 0.3) -> None:
    """Sleep in short intervals so KeyboardInterrupt is delivered on Windows."""
    remaining = seconds
    while remaining > 0:
        time.sleep(min(interval, remaining))
        remaining -= interval


def _build_metrics_table(title: str, metrics_list: List[dict]) -> Table:
    """Build a rich table for server metrics."""
    t = get_theme()
    table = Table(title=title, box=box.ROUNDED, show_lines=True)
    table.add_column("Server", style=t.col_server)
    table.add_column("IP", style=t.col_ip)
    table.add_column("CPU %", justify="right")
    table.add_column("RAM %", justify="right")
    table.add_column("Disk %", justify="right")
    table.add_column("Net ↑ MB/s", justify="right")
    table.add_column("Net ↓ MB/s", justify="right")

    for metric in metrics_list:
        table.add_row(
            metric["server"],
            metric["ip"],
            _format_metric_value(metric["cpu"], 1, color=True),
            _format_metric_value(metric["ram"], 1, color=True),
            _format_metric_value(metric["disk"], 1, color=True),
            _format_metric_value(metric["net_up"], 2),
            _format_metric_value(metric["net_down"], 2),
        )

    return table


def _collect_metrics_for_targets(
    target_servers,
    timeout: Optional[int],
    show_progress: bool = False,
) -> tuple[List[dict], List[dict]]:
    """Collect metrics from all target servers."""
    collector = MetricsCollector()
    results: List[dict] = []
    failures: List[dict] = []

    tasks: List[Tuple[Any, str]] = []
    for server in target_servers:
        for server_ip in server.ips:
            tasks.append((server, server_ip))

    total = len(tasks)
    status_ctx = None

    def _on_complete(done: int, total: int) -> None:
        if status_ctx is not None:
            status_ctx.update(
                styled(f"Collecting metrics [{done}/{total} targets]...", "progress")
            )

    def collect_target(task: Tuple[Any, str]) -> tuple[Optional[dict], Optional[dict]]:
        server, server_ip = task
        try:
            metrics = collector.collect_metrics(server, server_ip, timeout=timeout)
            return (
                {
                    "server": server.name,
                    "ip": server_ip,
                    "cpu": metrics.cpu_percent,
                    "ram": metrics.ram_percent,
                    "disk": metrics.disk_percent,
                    "net_up": metrics.network_up_mbps,
                    "net_down": metrics.network_down_mbps,
                },
                None,
            )
        except Exception as e:
            return (
                None,
                {
                    "server": server.name,
                    "ip": server_ip,
                    "error": str(e),
                },
            )

    if show_progress:
        status_ctx = _progress_console.status(
            styled(f"Collecting metrics [0/{total} targets]...", "progress"),
            spinner="dots",
        )
        status_ctx.start()

    try:
        for result, failure in parallel_map_ordered(
            tasks, collect_target, on_complete=_on_complete if show_progress else None
        ):
            if result:
                results.append(result)
            if failure:
                failures.append(failure)
    finally:
        if status_ctx is not None:
            status_ctx.stop()

    return results, failures


def top(
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
    monitor: bool = typer.Option(
        False, "--monitor", help="Continuously refresh metrics table until Ctrl+C"
    ),
    on_failure: Optional[str] = typer.Option(
        None, "--on-failure", help="Behavior on partial failure: continue|stop|prompt"
    ),
) -> None:
    """Display real-time system metrics for servers.

    Shows CPU, RAM, Disk, and Network metrics for all servers in the environment
    or filtered by --server or --ip flags.

    Examples:
        dagdi top                           # All servers in current context
        dagdi top -p myapp -e prod          # All servers in prod environment
        dagdi top --server web-1            # Specific server
        dagdi top --ip 10.0.1.10            # Specific IP
    """
    try:
        # Load configuration
        yaml_configs = load_all_configurations()
        merged_config = merge_configurations(yaml_configs)
        config = validate_configuration(merged_config)
        config = resolve_services(config)

        # Load context
        current_context = get_context()

        # Resolve scope
        scope = resolve_scope(
            config=config,
            product=product or (current_context.get("product") if current_context else None),
            environment=environment or (current_context.get("environment") if current_context else None),
            server=server,
            ip=ip,
        )

        # Get target servers
        target_servers = scope.servers

        if not target_servers:
            typer.echo("No servers found matching the specified scope.")
            raise typer.Exit(1)

        if monitor:
            live = Live(
                _build_metrics_table("System Metrics (Monitoring)", []),
                refresh_per_second=4,
                transient=False,
            )
            live.start()
            previous_values = {}
            try:
                while True:
                    results, failures = _collect_metrics_for_targets(target_servers, timeout)
                    display_results, previous_values = _apply_monitor_change_highlights(
                        results, previous_values
                    )
                    live.update(
                        _build_metrics_table("System Metrics (Monitoring)", display_results)
                    )
                    if failures:
                        typer.echo(f"\n⚠️  {len(failures)} target(s) failed in latest refresh.")
                    _interruptible_sleep(2)
            except KeyboardInterrupt:
                typer.echo("\nMonitoring stopped.")
                raise typer.Exit(0)
            finally:
                live.stop()

        results, failures = _collect_metrics_for_targets(
            target_servers, timeout, show_progress=True
        )

        # Display results
        formatter = Formatter()
        formatter.display_metrics_table(results)

        # Display summary
        if failures:
            typer.echo(f"\n⚠️  {len(failures)} target(s) failed:")
            for failure in failures:
                typer.echo(f"  [{failure['server']} | {failure['ip']}] {failure['error']}")

        # Display success summary
        typer.echo(
            f"\n✓ Collected metrics from {len(results)} target(s), {len(failures)} failed"
        )

        if failures and len(failures) == len(results) + len(failures):
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
