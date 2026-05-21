"""Output formatting utilities for Dagdi CLI."""

import re
from typing import List, Dict, Any, Optional

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree


console = Console()


# ---------------------------------------------------------------------------
# Metric color-coding
# ---------------------------------------------------------------------------

def colorize_metric(value: float, fmt: str = ".1f") -> str:
    if value >= 80:
        style = "bold red"
    elif value >= 50:
        style = "yellow"
    else:
        style = "green"
    return f"[{style}]{value:{fmt}}[/{style}]"


# ---------------------------------------------------------------------------
# Status indicators
# ---------------------------------------------------------------------------

_STATUS_INDICATORS = {
    "RUNNING": "[green]● RUNNING[/green]",
    "STOPPED": "[red]● STOPPED[/red]",
    "FAILED": "[bold red]● FAILED[/bold red]",
    "NOT_FOUND": "[dim]● NOT_FOUND[/dim]",
    "UNKNOWN": "[yellow]● UNKNOWN[/yellow]",
}


def format_status_indicator(status: str) -> str:
    return _STATUS_INDICATORS.get(status, f"[yellow]● {status}[/yellow]")


# ---------------------------------------------------------------------------
# Log-level highlighting
# ---------------------------------------------------------------------------

_LOG_LEVEL_STYLES = {
    "ERROR": "bold red",
    "FATAL": "bold red",
    "WARN": "yellow",
    "WARNING": "yellow",
    "INFO": "blue",
    "DEBUG": "dim",
    "TRACE": "dim",
}

_LOG_LEVEL_PATTERN = re.compile(
    r"\b(" + "|".join(_LOG_LEVEL_STYLES.keys()) + r")\b",
    re.IGNORECASE,
)


def highlight_log_line(line: str) -> str:
    def _replace(match: re.Match) -> str:
        level = match.group(0).upper()
        key = "WARN" if level == "WARNING" else level
        style = _LOG_LEVEL_STYLES.get(key, "")
        if style:
            return f"[{style}]{match.group(0)}[/{style}]"
        return match.group(0)

    return _LOG_LEVEL_PATTERN.sub(_replace, line)


def format_table(
    title: str,
    columns: List[str],
    rows: List[List[str]],
    show_header: bool = True
) -> None:
    """
    Display a formatted table using rich library.
    
    Args:
        title: Table title
        columns: List of column headers
        rows: List of rows, each row is a list of strings
        show_header: Whether to show column headers
    """
    table = Table(title=title, show_header=show_header, box=box.ROUNDED, show_lines=True)
    
    for column in columns:
        table.add_column(column)
    
    for row in rows:
        table.add_row(*row)
    
    console.print(table)


def format_hierarchical(
    product_name: str,
    environment_name: str,
    servers: List[Dict[str, Any]],
) -> None:
    tree = Tree(
        f"[bold blue]{product_name}[/bold blue] / "
        f"[bold blue]{environment_name}[/bold blue]"
    )

    for server in servers:
        server_label = (
            f"[bold cyan]{server['name']}[/bold cyan] ({server['type']})"
        )
        server_branch = tree.add(server_label)

        for ip in server.get("ips", []):
            server_branch.add(f"[dim]IP:[/dim] {ip}")

        services = server.get("services", [])
        if services:
            svc_branch = server_branch.add("[bold green]Services[/bold green]")
            for service in services:
                friendly_name = service.get("friendly_name")
                if friendly_name:
                    svc_label = (
                        f"{friendly_name} [{service['name']}] ({service['type']})"
                    )
                else:
                    svc_label = f"{service['name']} ({service['type']})"
                svc_node = svc_branch.add(svc_label)

                if service.get("api_endpoint"):
                    svc_node.add(f"[dim]API:[/dim] {service['api_endpoint']}")
                if service.get("port") is not None:
                    svc_node.add(f"[dim]Port:[/dim] {service['port']}")
                if service.get("log_location"):
                    svc_node.add(f"[dim]Log:[/dim] {service['log_location']}")
        else:
            server_branch.add("[dim]No services[/dim]")

    console.print()
    console.print(tree)
    console.print()


def format_error(
    title: str,
    details: str,
    suggestion: Optional[str] = None,
    available_options: Optional[List[str]] = None
) -> None:
    """
    Display a formatted error message.
    
    Args:
        title: Error title
        details: Error details
        suggestion: Optional suggestion for fixing the error
        available_options: Optional list of available options
    """
    console.print(f"\n[bold red]ERROR:[/bold red] {title}")
    console.print(f"  [yellow]Details:[/yellow] {details}")
    
    if suggestion:
        console.print(f"  [cyan]Suggestion:[/cyan] {suggestion}")
    
    if available_options:
        console.print(f"  [cyan]Available options:[/cyan]")
        for option in available_options:
            console.print(f"    • {option}")
    
    console.print()


def format_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def format_info(message: str) -> None:
    """Display an info message."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def format_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


class Formatter:
    """Formatter class for displaying various output types."""

    @staticmethod
    def display_metrics_table(metrics_list: List[Dict[str, Any]]) -> None:
        table = Table(title="System Metrics", box=box.ROUNDED, show_lines=True)
        table.add_column("Server", style="cyan")
        table.add_column("IP", style="magenta")
        table.add_column("CPU %", justify="right")
        table.add_column("RAM %", justify="right")
        table.add_column("Disk %", justify="right")
        table.add_column("Net ↑ MB/s", justify="right")
        table.add_column("Net ↓ MB/s", justify="right")

        for metric in metrics_list:
            table.add_row(
                metric["server"],
                metric["ip"],
                colorize_metric(metric["cpu"]),
                colorize_metric(metric["ram"]),
                colorize_metric(metric["disk"]),
                f"{metric['net_up']:.2f}",
                f"{metric['net_down']:.2f}",
            )

        console.print(table)
