"""Output formatting utilities for Dagdi CLI."""

import re
from typing import List, Dict, Any, Optional

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .themes import get_theme, styled


console = Console()


# ---------------------------------------------------------------------------
# Metric color-coding
# ---------------------------------------------------------------------------

def colorize_metric(value: float, fmt: str = ".1f") -> str:
    t = get_theme()
    if value >= 80:
        style = t.metric_critical
    elif value >= 50:
        style = t.metric_warning
    else:
        style = t.metric_normal
    if not style:
        return f"{value:{fmt}}"
    return f"[{style}]{value:{fmt}}[/{style}]"


# ---------------------------------------------------------------------------
# Status indicators
# ---------------------------------------------------------------------------

def format_status_indicator(status: str) -> str:
    t = get_theme()
    _STATUS_ROLE = {
        "RUNNING": t.status_running,
        "STOPPED": t.status_stopped,
        "FAILED": t.status_failed,
        "NOT_FOUND": t.status_not_found,
        "UNKNOWN": t.status_unknown,
    }
    style = _STATUS_ROLE.get(status, t.status_unknown)
    if not style:
        return f"● {status}"
    return f"[{style}]● {status}[/{style}]"


# ---------------------------------------------------------------------------
# Log-level highlighting
# ---------------------------------------------------------------------------

_LOG_LEVEL_KEYS = ["ERROR", "FATAL", "WARN", "WARNING", "INFO", "DEBUG", "TRACE"]

_LOG_LEVEL_PATTERN = re.compile(
    r"\b(" + "|".join(_LOG_LEVEL_KEYS) + r")\b",
    re.IGNORECASE,
)


def _log_level_role(level: str) -> str:
    t = get_theme()
    _mapping = {
        "ERROR": t.log_error,
        "FATAL": t.log_error,
        "WARN": t.log_warn,
        "WARNING": t.log_warn,
        "INFO": t.log_info,
        "DEBUG": t.log_debug,
        "TRACE": t.log_debug,
    }
    return _mapping.get(level, "")


def highlight_log_line(line: str) -> str:
    def _replace(match: re.Match) -> str:
        level = match.group(0).upper()
        key = "WARN" if level == "WARNING" else level
        style = _log_level_role(key)
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
    t = get_theme()
    tree = Tree(
        f"{styled(product_name, 'product')} / "
        f"{styled(environment_name, 'product')}"
    )

    for server in servers:
        server_label = f"{styled(server['name'], 'server')} ({server['type']})"
        server_branch = tree.add(server_label)

        for ip in server.get("ips", []):
            server_branch.add(f"{styled('IP:', 'label')} {ip}")

        services = server.get("services", [])
        if services:
            svc_branch = server_branch.add(styled("Services", "service"))
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
                    svc_node.add(
                        f"{styled('API:', 'label')} {service['api_endpoint']}"
                    )
                if service.get("port") is not None:
                    svc_node.add(
                        f"{styled('Port:', 'label')} {service['port']}"
                    )
                if service.get("log_location"):
                    svc_node.add(
                        f"{styled('Log:', 'label')} {service['log_location']}"
                    )
        else:
            server_branch.add(styled("No services", "label"))

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
    console.print(f"\n{styled('ERROR:', 'error')} {title}")
    console.print(f"  {styled('Details:', 'detail')} {details}")

    if suggestion:
        console.print(f"  {styled('Suggestion:', 'suggestion')} {suggestion}")

    if available_options:
        console.print(f"  {styled('Available options:', 'suggestion')}")
        for option in available_options:
            console.print(f"    • {option}")

    console.print()


def format_success(message: str) -> None:
    """Display a success message."""
    console.print(f"{styled('✓', 'success')} {message}")


def format_info(message: str) -> None:
    """Display an info message."""
    console.print(f"{styled('ℹ', 'info')} {message}")


def format_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"{styled('⚠', 'warning')} {message}")


class Formatter:
    """Formatter class for displaying various output types."""

    @staticmethod
    def display_metrics_table(metrics_list: List[Dict[str, Any]]) -> None:
        t = get_theme()
        table = Table(title="System Metrics", box=box.ROUNDED, show_lines=True)
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
                colorize_metric(metric["cpu"]),
                colorize_metric(metric["ram"]),
                colorize_metric(metric["disk"]),
                f"{metric['net_up']:.2f}",
                f"{metric['net_down']:.2f}",
            )

        console.print(table)
