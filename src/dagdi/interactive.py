"""Interactive selection prompts for Dagdi CLI.

Provides two tiers of interactivity:
- Fuzzy-searchable selection via InquirerPy (when installed)
- Numbered list fallback via Rich prompts (always available)
"""

from typing import List, Optional

from rich import box
from rich.console import Console
from rich.table import Table

from dagdi.models import Service

VALID_ACTIONS = ["status", "start", "stop", "restart"]


def _has_inquirer() -> bool:
    try:
        from InquirerPy import inquirer  # noqa: F401
        return True
    except ImportError:
        return False


def _service_display(svc: Service) -> str:
    if svc.friendly_name:
        return f"{svc.friendly_name} ({svc.name})"
    return svc.name


def _deduplicate_services(services: List[Service]) -> List[Service]:
    """Deduplicate services by canonical name, preserving order."""
    seen: set = set()
    unique: List[Service] = []
    for svc in services:
        if svc.name not in seen:
            seen.add(svc.name)
            unique.append(svc)
    return unique


# ---------------------------------------------------------------------------
# Rich / numbered-list fallback (Option 1)
# ---------------------------------------------------------------------------

def _numbered_select_service(services: List[Service]) -> Optional[Service]:
    console = Console()
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Service", style="green")
    table.add_column("Type", style="dim")

    for idx, svc in enumerate(services, 1):
        table.add_row(str(idx), _service_display(svc), svc.type)

    console.print(table)

    while True:
        try:
            raw = console.input("[bold]Select a service [1-{}]: [/bold]".format(len(services)))
        except (EOFError, KeyboardInterrupt):
            return None
        try:
            choice = int(raw.strip())
            if 1 <= choice <= len(services):
                return services[choice - 1]
        except ValueError:
            pass
        console.print(f"[red]Please enter a number between 1 and {len(services)}[/red]")


def _numbered_select_services(services: List[Service]) -> List[Service]:
    console = Console()
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Service", style="green")
    table.add_column("Type", style="dim")

    for idx, svc in enumerate(services, 1):
        table.add_row(str(idx), _service_display(svc), svc.type)

    console.print(table)
    console.print("[dim]Enter comma-separated numbers (e.g. 1,3,4) or 'all'[/dim]")

    while True:
        try:
            raw = console.input("[bold]Select services: [/bold]")
        except (EOFError, KeyboardInterrupt):
            return []
        stripped = raw.strip().lower()
        if stripped == "all":
            return list(services)
        try:
            indices = [int(x.strip()) for x in stripped.split(",")]
            if all(1 <= i <= len(services) for i in indices):
                return [services[i - 1] for i in indices]
        except ValueError:
            pass
        console.print(
            f"[red]Enter numbers between 1 and {len(services)}, separated by commas[/red]"
        )


def _numbered_select_action() -> Optional[str]:
    console = Console()
    for idx, action in enumerate(VALID_ACTIONS, 1):
        console.print(f"  [cyan]{idx}[/cyan]. {action}")

    while True:
        try:
            raw = console.input(
                "[bold]Select an action [1-{}]: [/bold]".format(len(VALID_ACTIONS))
            )
        except (EOFError, KeyboardInterrupt):
            return None
        try:
            choice = int(raw.strip())
            if 1 <= choice <= len(VALID_ACTIONS):
                return VALID_ACTIONS[choice - 1]
        except ValueError:
            pass
        console.print(f"[red]Please enter a number between 1 and {len(VALID_ACTIONS)}[/red]")


# ---------------------------------------------------------------------------
# InquirerPy fuzzy selection (Option 2)
# ---------------------------------------------------------------------------

def _fuzzy_select_service(services: List[Service]) -> Optional[Service]:
    from InquirerPy import inquirer

    choices = [{"name": _service_display(svc), "value": svc} for svc in services]
    try:
        return inquirer.fuzzy(
            message="Select a service:",
            choices=choices,
            max_height="60%",
        ).execute()
    except (EOFError, KeyboardInterrupt):
        return None


def _fuzzy_select_services(services: List[Service]) -> List[Service]:
    from InquirerPy import inquirer

    choices = [{"name": _service_display(svc), "value": svc} for svc in services]
    try:
        result = inquirer.checkbox(
            message="Select services (space to toggle, enter to confirm):",
            choices=choices,
            instruction="(type to filter)",
        ).execute()
        return result or []
    except (EOFError, KeyboardInterrupt):
        return []


def _fuzzy_select_action() -> Optional[str]:
    from InquirerPy import inquirer

    try:
        return inquirer.select(
            message="Select an action:",
            choices=VALID_ACTIONS,
        ).execute()
    except (EOFError, KeyboardInterrupt):
        return None


# ---------------------------------------------------------------------------
# Public API — auto-selects fuzzy or numbered based on availability
# ---------------------------------------------------------------------------

def select_service(services: List[Service]) -> Optional[Service]:
    """Prompt the user to pick a single service."""
    services = _deduplicate_services(services)
    if not services:
        return None
    if len(services) == 1:
        return services[0]
    if _has_inquirer():
        return _fuzzy_select_service(services)
    return _numbered_select_service(services)


def select_services(services: List[Service]) -> List[Service]:
    """Prompt the user to pick one or more services."""
    services = _deduplicate_services(services)
    if not services:
        return []
    if _has_inquirer():
        return _fuzzy_select_services(services)
    return _numbered_select_services(services)


def select_action() -> Optional[str]:
    """Prompt the user to pick an action (status/start/stop/restart)."""
    if _has_inquirer():
        return _fuzzy_select_action()
    return _numbered_select_action()
