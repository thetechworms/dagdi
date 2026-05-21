"""Log streaming commands for Dagdi CLI."""

import queue
import socket
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

import typer
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from dagdi.config.loader import load_all_configurations
from dagdi.config.merger import merge_configurations
from dagdi.config.validator import validate_configuration
from dagdi.config.resolver import resolve_services
from dagdi.context.manager import get_context
from dagdi.models import Server, Service
from dagdi.output.formatter import highlight_log_line
from dagdi.resolver import resolve_scope

_LABEL_COLORS = [
    "cyan", "green", "yellow", "magenta", "blue", "bright_red",
    "bright_cyan", "bright_green", "bright_yellow", "bright_magenta",
]

logs_app = typer.Typer(help="Log streaming commands")


@dataclass
class _LogTarget:
    server: Server
    ip: str
    service: Service
    command: str
    label: str
    color: str


@dataclass
class _LogLine:
    target: _LogTarget
    text: str
    is_error: bool = False
    is_eof: bool = False


def _build_log_command(service_obj, use_sudo: bool = False) -> str:
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


def _resolve_log_targets(
    servers: List[Server],
    service_names: List[str],
) -> List["_LogTarget"]:
    """Match service names to servers and build concrete log targets."""
    targets: List[_LogTarget] = []
    color_idx = 0

    for svc_name in service_names:
        svc_key = svc_name.strip().lower()
        for server_obj in servers:
            service_obj = None
            for svc in server_obj.services:
                friendly = (svc.friendly_name or "").strip().lower()
                if svc.name == svc_name or friendly == svc_key:
                    service_obj = svc
                    break

            if service_obj is None or not server_obj.ips:
                continue

            ssh_user = (server_obj.ssh_config.username or "").strip().lower()
            use_sudo = server_obj.ssh_config.sudo and ssh_user != "root"
            cmd = _build_log_command(service_obj, use_sudo=use_sudo)

            display_name = service_obj.friendly_name or service_obj.name
            label = f"{server_obj.name}/{display_name}"
            color = _LABEL_COLORS[color_idx % len(_LABEL_COLORS)]
            color_idx += 1

            targets.append(_LogTarget(
                server=server_obj,
                ip=server_obj.ips[0],
                service=service_obj,
                command=cmd,
                label=label,
                color=color,
            ))

    return targets


def _stream_ssh_target(
    target: _LogTarget,
    line_queue: "queue.Queue[_LogLine]",
    stop_event: threading.Event,
) -> None:
    """Stream logs from a remote target via SSH."""
    from dagdi.ssh.connection_pool import get_connection_pool
    from dagdi.ssh.executor import _normalize_sudo_command

    buf = ""
    try:
        pool = get_connection_pool()
        command = _normalize_sudo_command(target.server, target.ip, target.command)
        client = pool.get(target.server.name, target.ip, target.server.ssh_config)
        _, stdout, _ = client.exec_command(command)
        channel = stdout.channel
        channel.settimeout(0.5)

        while not stop_event.is_set():
            try:
                data = channel.recv(4096)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line_queue.put(_LogLine(target=target, text=line))
            except socket.timeout:
                if channel.exit_status_ready() and not channel.recv_ready():
                    break
    except Exception as e:
        line_queue.put(_LogLine(target=target, text=str(e), is_error=True))
    finally:
        if buf:
            line_queue.put(_LogLine(target=target, text=buf))
        line_queue.put(_LogLine(target=target, text="", is_eof=True))


def _stream_local_target(
    target: _LogTarget,
    line_queue: "queue.Queue[_LogLine]",
    stop_event: threading.Event,
) -> None:
    """Stream logs from a local subprocess."""
    process = None
    try:
        process = subprocess.Popen(
            target.command,
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            if stop_event.is_set():
                break
            line_queue.put(_LogLine(target=target, text=raw_line.rstrip("\n")))
    except Exception as e:
        line_queue.put(_LogLine(target=target, text=str(e), is_error=True))
    finally:
        line_queue.put(_LogLine(target=target, text="", is_eof=True))
        if process is not None:
            process.terminate()


def _start_stream_threads(
    targets: List[_LogTarget],
    line_queue: "queue.Queue[_LogLine]",
    stop_event: threading.Event,
) -> List[threading.Thread]:
    """Start a streaming thread per target."""
    from dagdi.ssh.executor import _is_local_target

    threads: List[threading.Thread] = []
    for target in targets:
        fn = _stream_local_target if _is_local_target(target.ip) else _stream_ssh_target
        t = threading.Thread(target=fn, args=(target, line_queue, stop_event), daemon=True)
        t.start()
        threads.append(t)
    return threads


def _display_interleaved(
    targets: List[_LogTarget],
    line_queue: "queue.Queue[_LogLine]",
    stop_event: threading.Event,
) -> None:
    """Merge all log streams into a single output with colored prefixes."""
    console = Console(highlight=False)
    active = len(targets)
    max_label = max((len(t.label) for t in targets), default=0)

    while active > 0 and not stop_event.is_set():
        try:
            log_line = line_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        padded = log_line.target.label.ljust(max_label)
        prefix = f"[{log_line.target.color}]{padded}[/{log_line.target.color}]"

        if log_line.is_eof:
            active -= 1
            console.print(f"{prefix} [dim]-- stream ended --[/dim]")
            continue

        if log_line.is_error:
            console.print(f"{prefix} [red]{log_line.text}[/red]")
        else:
            highlighted = highlight_log_line(log_line.text)
            console.print(f"{prefix} {highlighted}")


_SCROLL_BUFFER_SIZE = 5000


class _SplitView:
    """Renderable that Rich Live queries on its own refresh timer.

    Supports scrollable per-panel buffers with an active panel indicator.
    The main loop writes to shared buffers and offsets; Live reads them
    when it decides to repaint.
    """

    def __init__(
        self,
        targets: List[_LogTarget],
        buffers: dict,
        active: set,
        panel_height: int,
        offsets: dict,
        active_idx: List[int],
        paused: List[bool],
        fullscreen: List[bool],
    ):
        self._targets = targets
        self._buffers = buffers
        self._active = active
        self._panel_height = panel_height
        self._offsets = offsets
        self._active_idx = active_idx
        self._paused = paused
        self._fullscreen = fullscreen

    def _render_panel(self, idx: int, height: int) -> Layout:
        t = self._targets[idx]
        visible_lines = height - 2
        buf = list(self._buffers[t.label])
        offset = self._offsets.get(t.label, 0)
        max_offset = max(0, len(buf) - visible_lines)
        offset = min(offset, max_offset)

        if offset == 0:
            visible = buf[-visible_lines:] if buf else []
        else:
            end_idx = len(buf) - offset
            start_idx = max(0, end_idx - visible_lines)
            visible = buf[start_idx:end_idx]

        if visible:
            content = Text.from_markup("\n".join(visible))
        else:
            content = Text("(waiting for logs...)", style="dim")

        is_active = idx == self._active_idx[0]
        is_streaming = t.label in self._active

        if is_active:
            border = "bold " + t.color
        elif is_streaming:
            border = t.color
        else:
            border = "dim"

        title = f"[{t.color}]{t.label}[/{t.color}]"
        status_parts = []
        if self._paused[0]:
            status_parts.append("PAUSED")
        if offset > 0:
            status_parts.append(f"+{offset}")
        if status_parts:
            title += f" [dim]({' '.join(status_parts)})[/dim]"

        subtitle = "[dim]active[/dim]" if is_active else None

        panel = Panel(
            content,
            title=title,
            subtitle=subtitle,
            border_style=border,
            height=height,
        )
        return Layout(panel, name=t.label)

    def __rich__(self):
        main_layout = Layout()

        if self._fullscreen[0]:
            idx = self._active_idx[0]
            full_height = self._panel_height * len(self._targets)
            panel_layout = self._render_panel(idx, full_height)
        else:
            children = []
            for i in range(len(self._targets)):
                children.append(self._render_panel(i, self._panel_height))
            panel_layout = Layout()
            panel_layout.split_column(*children)

        pause_label = "Space Resume" if self._paused[0] else "Space Pause"
        fs_label = "Enter Restore" if self._fullscreen[0] else "Enter Fullscreen"
        footer = Layout(
            Text(
                f" ↑↓ Scroll  PgUp/PgDn Page  Tab Switch  End Follow  "
                f"{pause_label}  {fs_label}  Ctrl+C Quit ",
                style="black on white",
            ),
            size=1,
        )
        main_layout.split_column(panel_layout, footer)
        return main_layout


def _read_keys(
    key_queue: "queue.Queue[str]",
    stop_event: threading.Event,
) -> None:
    """Read keyboard input in a background thread."""
    try:
        if sys.platform == "win32":
            _read_keys_windows(key_queue, stop_event)
        else:
            _read_keys_unix(key_queue, stop_event)
    except Exception:
        pass


def _read_keys_windows(
    key_queue: "queue.Queue[str]",
    stop_event: threading.Event,
) -> None:
    import msvcrt
    import time

    while not stop_event.is_set():
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b"\xe0", b"\x00"):
                key2 = msvcrt.getch()
                action = {
                    b"H": "up", b"P": "down",
                    b"I": "pgup", b"Q": "pgdn",
                    b"G": "home", b"O": "end",
                }.get(key2)
                if action:
                    key_queue.put(action)
            elif key == b"\t":
                key_queue.put("tab")
            elif key == b" ":
                key_queue.put("pause")
            elif key == b"\r":
                key_queue.put("fullscreen")
        else:
            time.sleep(0.05)


def _read_keys_unix(
    key_queue: "queue.Queue[str]",
    stop_event: threading.Event,
) -> None:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not stop_event.is_set():
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        ch2 = sys.stdin.read(1)
                        if ch2 == "[" and select.select([sys.stdin], [], [], 0.05)[0]:
                            ch3 = sys.stdin.read(1)
                            if ch3 in ("5", "6") and select.select([sys.stdin], [], [], 0.05)[0]:
                                sys.stdin.read(1)
                            action = {
                                "A": "up", "B": "down",
                                "5": "pgup", "6": "pgdn",
                                "H": "home", "F": "end",
                            }.get(ch3)
                            if action:
                                key_queue.put(action)
                elif ch == "\t":
                    key_queue.put("tab")
                elif ch == " ":
                    key_queue.put("pause")
                elif ch in ("\r", "\n"):
                    key_queue.put("fullscreen")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _display_split(
    targets: List[_LogTarget],
    line_queue: "queue.Queue[_LogLine]",
    stop_event: threading.Event,
    buffer_size: int = _SCROLL_BUFFER_SIZE,
) -> None:
    """Display each service stream in its own scrollable Rich panel."""
    console = Console()
    panel_height = max(7, (console.size.height - 2) // len(targets))
    content_lines = panel_height - 2

    buffers: dict[str, deque] = {
        t.label: deque(maxlen=buffer_size) for t in targets
    }
    active = {t.label for t in targets}
    offsets: dict[str, int] = {t.label: 0 for t in targets}
    active_idx: List[int] = [0]
    paused: List[bool] = [False]
    fullscreen: List[bool] = [False]

    view = _SplitView(
        targets, buffers, active, panel_height, offsets,
        active_idx, paused, fullscreen,
    )

    key_queue: queue.Queue[str] = queue.Queue()
    key_thread = threading.Thread(
        target=_read_keys, args=(key_queue, stop_event), daemon=True,
    )
    key_thread.start()

    with Live(view, refresh_per_second=4, console=console, screen=True):
        while active and not stop_event.is_set():
            # Process keyboard events
            while not key_queue.empty():
                try:
                    action = key_queue.get_nowait()
                except queue.Empty:
                    break

                if action == "pause":
                    paused[0] = not paused[0]
                    continue
                if action == "fullscreen":
                    fullscreen[0] = not fullscreen[0]
                    continue

                label = targets[active_idx[0]].label
                if fullscreen[0]:
                    fs_lines = panel_height * len(targets) - 2
                    buf_len = len(buffers[label])
                    max_off = max(0, buf_len - fs_lines)
                else:
                    buf_len = len(buffers[label])
                    max_off = max(0, buf_len - content_lines)

                if action == "up":
                    offsets[label] = min(max_off, offsets[label] + 1)
                elif action == "down":
                    offsets[label] = max(0, offsets[label] - 1)
                elif action == "pgup":
                    page = (panel_height * len(targets) - 2) if fullscreen[0] else content_lines
                    offsets[label] = min(max_off, offsets[label] + page)
                elif action == "pgdn":
                    page = (panel_height * len(targets) - 2) if fullscreen[0] else content_lines
                    offsets[label] = max(0, offsets[label] - page)
                elif action == "home":
                    offsets[label] = max_off
                elif action == "end":
                    offsets[label] = 0
                elif action == "tab":
                    active_idx[0] = (active_idx[0] + 1) % len(targets)

            # Process log lines
            try:
                log_line = line_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if log_line.is_eof:
                active.discard(log_line.target.label)
                buffers[log_line.target.label].append("[dim]-- stream ended --[/dim]")
                continue

            if paused[0]:
                continue

            text = (
                f"[red]{log_line.text}[/red]"
                if log_line.is_error
                else highlight_log_line(log_line.text)
            )
            buffers[log_line.target.label].append(text)

            # Keep scrolled view stable when new lines arrive
            if offsets[log_line.target.label] > 0:
                offsets[log_line.target.label] += 1


@logs_app.command()
def logs(
    service_names: Optional[List[str]] = typer.Argument(
        None, help="Service names to stream (interactive if omitted)"
    ),
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
    layout: str = typer.Option(
        "interleaved", "--layout", help="Display layout: interleaved or split"
    ),
) -> None:
    """Stream logs from one or more services.

    Examples:
        dagdi logs                              # Interactive service selection
        dagdi logs nginx                        # Single service
        dagdi logs nginx api                    # Multiple services (interleaved)
        dagdi logs nginx api --layout split     # Multiple services (split panels)
        dagdi logs nginx -p app -e prod         # With product and environment
        dagdi logs nginx --server web-1         # From specific server
    """
    try:
        if layout not in ("interleaved", "split"):
            typer.echo(
                f"Error: Invalid layout '{layout}'. Must be 'interleaved' or 'split'",
                err=True,
            )
            raise typer.Exit(1)

        # Load configuration
        yaml_configs = load_all_configurations()
        merged_config = merge_configurations(yaml_configs)
        config = validate_configuration(merged_config)
        config = resolve_services(config)

        # Load context + resolve scope
        current_context = get_context()
        scope = resolve_scope(
            config=config,
            product=product or (current_context.get("product") if current_context else None),
            environment=environment or (
                current_context.get("environment") if current_context else None
            ),
            server=server,
            ip=ip,
        )

        # Interactive selection when no services specified
        if not service_names:
            from dagdi.interactive import select_services as interactive_select

            seen: set = set()
            available: List[Service] = []
            for srv in scope.servers:
                for svc in srv.services:
                    if svc.name not in seen:
                        seen.add(svc.name)
                        available.append(svc)

            if not available:
                typer.echo("No services found in the current scope.", err=True)
                raise typer.Exit(1)

            selected = interactive_select(available)
            if not selected:
                raise typer.Exit(0)
            service_names = [svc.name for svc in selected]

        # Resolve concrete targets
        targets = _resolve_log_targets(scope.servers, service_names)

        if not targets:
            svc_list = ", ".join(service_names)
            typer.echo(f"Error: No matching services found: {svc_list}", err=True)
            raise typer.Exit(1)

        # Warm up SSH connections and resolve sudo credentials before streaming.
        # Interactive prompts (SSH password, sudo password) conflict with Rich
        # Live rendering and threaded streams, so all auth must happen upfront.
        from dagdi.ssh.executor import (
            warm_up_connection, prepare_sudo_auth, validate_sudo_auth, _is_local_target,
        )

        for target in targets:
            if _is_local_target(target.ip):
                continue
            warm_up_connection(target.server, target.ip)
            if target.server.ssh_config.sudo:
                prepare_sudo_auth(target.server, target.ip)
                validate_sudo_auth(target.server, target.ip)

        # Print header
        target_summary = ", ".join(t.label for t in targets)
        typer.echo(f"Streaming logs from: {target_summary}")
        typer.echo(f"Layout: {layout} | Press Ctrl+C to stop.\n")

        # Start streaming
        line_queue: queue.Queue[_LogLine] = queue.Queue()
        stop_event = threading.Event()
        _start_stream_threads(targets, line_queue, stop_event)

        try:
            if layout == "split":
                _display_split(
                    targets, line_queue, stop_event,
                    buffer_size=config.global_settings.log_buffer_size,
                )
            else:
                _display_interleaved(targets, line_queue, stop_event)
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            typer.echo("\n\nLog streaming stopped.")

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
