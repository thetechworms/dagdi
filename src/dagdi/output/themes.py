"""Theme system for Dagdi CLI output styling."""

from dataclasses import dataclass, fields
from typing import Dict, Optional


@dataclass
class Theme:
    """Defines all semantic color roles used across Dagdi CLI output.

    Each field maps a UI role to a Rich style string (e.g. "bold green",
    "cyan", "dim").  An empty string means no styling.
    """

    # -- status indicators --
    status_running: str = "green"
    status_stopped: str = "red"
    status_failed: str = "bold red"
    status_not_found: str = "dim"
    status_unknown: str = "yellow"

    # -- metric thresholds --
    metric_normal: str = "green"
    metric_warning: str = "yellow"
    metric_critical: str = "bold red"
    metric_changed: str = "bold bright_yellow"

    # -- log levels --
    log_error: str = "bold red"
    log_warn: str = "yellow"
    log_info: str = "blue"
    log_debug: str = "dim"

    # -- messages --
    error: str = "bold red"
    warning: str = "bold yellow"
    success: str = "bold green"
    info: str = "bold blue"
    detail: str = "yellow"
    suggestion: str = "cyan"

    # -- hierarchy / tree --
    product: str = "bold blue"
    server: str = "bold cyan"
    service: str = "bold green"
    label: str = "dim"

    # -- table columns --
    col_server: str = "cyan"
    col_ip: str = "magenta"
    col_service: str = "green"
    col_type: str = "blue"
    col_result: str = "yellow"
    col_metric: str = "magenta"
    col_pid: str = "cyan"
    col_since: str = "blue"

    # -- interactive elements --
    highlight: str = "cyan"
    username: str = "yellow"
    progress: str = "bold blue"
    panel_active: str = "green"
    panel_inactive: str = "blue"
    panel_warning: str = "yellow"
    error_text: str = "red"
    bold: str = "bold"
    title: str = "bold cyan"
    number: str = "bold yellow"


THEMES: Dict[str, Theme] = {
    "default": Theme(),

    "light": Theme(
        status_running="dark_green",
        status_stopped="dark_red",
        status_failed="bold dark_red",
        status_unknown="dark_orange",
        metric_normal="dark_green",
        metric_warning="dark_orange",
        metric_critical="bold dark_red",
        metric_changed="bold dark_orange",
        log_error="bold dark_red",
        log_warn="dark_orange",
        log_info="dark_blue",
        error="bold dark_red",
        warning="bold dark_orange",
        success="bold dark_green",
        info="bold dark_blue",
        detail="dark_orange",
        suggestion="dark_cyan",
        product="bold dark_blue",
        server="bold dark_cyan",
        service="bold dark_green",
        col_server="dark_cyan",
        col_ip="dark_magenta",
        col_service="dark_green",
        col_type="dark_blue",
        col_result="dark_orange",
        col_metric="dark_magenta",
        col_pid="dark_cyan",
        col_since="dark_blue",
        highlight="dark_cyan",
        username="dark_orange",
        progress="bold dark_blue",
        panel_active="dark_green",
        panel_inactive="dark_blue",
        panel_warning="dark_orange",
        error_text="dark_red",
        title="bold dark_cyan",
    ),

    "dark": Theme(
        status_running="bright_green",
        status_stopped="bright_red",
        status_failed="bold bright_red",
        status_unknown="bright_yellow",
        metric_normal="bright_green",
        metric_warning="bright_yellow",
        metric_critical="bold bright_red",
        log_error="bold bright_red",
        log_warn="bright_yellow",
        log_info="bright_blue",
        error="bold bright_red",
        warning="bold bright_yellow",
        success="bold bright_green",
        info="bold bright_blue",
        detail="bright_yellow",
        suggestion="bright_cyan",
        product="bold bright_blue",
        server="bold bright_cyan",
        service="bold bright_green",
        col_server="bright_cyan",
        col_ip="bright_magenta",
        col_service="bright_green",
        col_type="bright_blue",
        col_result="bright_yellow",
        col_metric="bright_magenta",
        col_pid="bright_cyan",
        col_since="bright_blue",
        highlight="bright_cyan",
        username="bright_yellow",
        progress="bold bright_blue",
        panel_active="bright_green",
        panel_inactive="bright_blue",
        panel_warning="bright_yellow",
        error_text="bright_red",
        title="bold bright_cyan",
    ),

    "no_color": Theme(**{f.name: "" for f in fields(Theme)}),
}

AVAILABLE_THEMES = sorted(THEMES.keys())

_active_theme: Theme = THEMES["default"]


def set_theme(name: str) -> None:
    """Activate a built-in theme by name."""
    global _active_theme
    if name not in THEMES:
        raise ValueError(
            f"Unknown theme '{name}'. Available themes: {', '.join(AVAILABLE_THEMES)}"
        )
    _active_theme = THEMES[name]


def get_theme() -> Theme:
    """Return the currently active theme."""
    return _active_theme


def styled(text: str, role: str) -> str:
    """Wrap *text* with the Rich markup for the given theme role.

    If the role resolves to an empty style (e.g. ``no_color`` theme),
    the text is returned unstyled.
    """
    style = getattr(_active_theme, role, "")
    if not style:
        return text
    return f"[{style}]{text}[/{style}]"
