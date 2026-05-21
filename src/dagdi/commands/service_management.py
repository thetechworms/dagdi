"""Service management commands for Dagdi CLI."""

from typing import Optional, List, Tuple, Dict, Any
import shlex
import time
import typer
from rich.console import Console as RichConsole

_progress_console = RichConsole()

from dagdi.concurrency import parallel_map_ordered
from dagdi.config.loader import load_all_configurations
from dagdi.config.merger import merge_configurations
from dagdi.config.validator import validate_configuration
from dagdi.config.resolver import resolve_services
from dagdi.context.manager import get_context
from dagdi.output.formatter import Formatter, format_status_indicator
from dagdi.resolver import resolve_scope, get_target_ips
from dagdi.ssh.executor import (
    execute_command,
    prepare_sudo_auth,
    validate_sudo_auth,
    warm_up_connection,
)
from dagdi.ssh.command_builder import CommandBuilder
from dagdi.models import ExecutionResult, Service

service_app = typer.Typer(help="Service management commands")


def _interruptible_sleep(seconds: float, interval: float = 0.3) -> None:
    """Sleep in short intervals so KeyboardInterrupt is delivered on Windows."""
    remaining = seconds
    while remaining > 0:
        time.sleep(min(interval, remaining))
        remaining -= interval


def _preflight_monitor_auth(target_ips: List[tuple]) -> None:
    """Resolve SSH and sudo credentials before starting live display.

    Interactive prompts (SSH password, sudo password) conflict with Rich Live
    rendering, so all credential resolution must happen before live.start().

    Raises on authentication failure so the caller can abort before rendering.
    """
    for server_obj, server_ip in target_ips:
        warm_up_connection(server_obj, server_ip)
        if server_obj.ssh_config.sudo:
            prepare_sudo_auth(server_obj, server_ip)
            validate_sudo_auth(server_obj, server_ip)


def _result_key(result: dict) -> str:
    """Build a stable key for a status result row."""
    return f"{result.get('server','')}|{result.get('ip','')}|{result.get('service','')}"


def _service_matches_identifier(service_obj: Service, identifier: str) -> bool:
    """Match a service by canonical name or friendly name."""
    key = identifier.strip().lower()
    return service_obj.name == identifier or (service_obj.friendly_name or "").strip().lower() == key


def _service_label(service_obj: Service) -> str:
    """Build display label for service."""
    if service_obj.friendly_name:
        return f"{service_obj.friendly_name} ({service_obj.name})"
    return service_obj.name


def _find_service_on_target(server_obj, name: str) -> Optional[Service]:
    """Resolve a service identifier on a server."""
    return next(
        (s for s in server_obj.services if _service_matches_identifier(s, name)),
        None,
    )


def _build_service_result(
    server_obj,
    server_ip: str,
    service_obj: Service,
    action: str,
    result: ExecutionResult,
) -> dict:
    """Convert an execution result into displayable output."""
    if action == "status":
        status = _parse_service_status(result, service_obj.type)
        metrics = _parse_service_metrics(result, service_obj.type)
        return {
            "server": server_obj.name,
            "ip": server_ip,
            "service": _service_label(service_obj),
            "service_type": service_obj.type,
            "pid": metrics["pid"],
            "cpu": metrics["cpu"],
            "ram": metrics["ram"],
            "since": metrics["since"],
            "status": status,
            "success": True,
        }

    return {
        "server": server_obj.name,
        "ip": server_ip,
        "service": _service_label(service_obj),
        "action": action,
        "success": result.success,
    }


def _build_service_failure(
    server_obj,
    server_ip: str,
    error: str,
    service_obj: Optional[Service] = None,
) -> dict:
    """Build a consistent failure payload."""
    failure = {
        "server": server_obj.name,
        "ip": server_ip,
        "error": error,
    }
    if service_obj:
        failure["service"] = _service_label(service_obj)
    return failure


def _execute_service_target(
    target: Tuple[Any, str],
    service_name: str,
    action: str,
    timeout: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[dict]]:
    """Execute a service action for a single target server/ip pair."""
    server_obj, server_ip = target
    service_obj = _find_service_on_target(server_obj, service_name)
    if not service_obj:
        return None, _build_service_failure(
            server_obj,
            server_ip,
            f"Service '{service_name}' not found on server",
        )

    try:
        if action == "status":
            cmd = _build_status_command_with_metrics(
                service_obj,
                server_type=server_obj.type,
                use_sudo=server_obj.ssh_config.sudo,
            )
        elif action == "start":
            cmd = CommandBuilder.get_start_command(
                service_obj,
                use_sudo=server_obj.ssh_config.sudo,
            )
        elif action == "stop":
            cmd = CommandBuilder.get_stop_command(
                service_obj,
                use_sudo=server_obj.ssh_config.sudo,
            )
        else:
            cmd = CommandBuilder.get_restart_command(
                service_obj,
                use_sudo=server_obj.ssh_config.sudo,
            )

        result = execute_command(server_obj, server_ip, cmd, timeout=timeout)

        if result.error:
            return None, _build_service_failure(
                server_obj, server_ip, result.error, service_obj=service_obj,
            )

        output = _build_service_result(server_obj, server_ip, service_obj, action, result)

        if action != "status" and not result.success:
            return output, _build_service_failure(
                server_obj,
                server_ip,
                result.stderr or result.stdout or "Unknown error",
                service_obj=service_obj,
            )
        return output, None
    except Exception as e:
        return None, _build_service_failure(
            server_obj,
            server_ip,
            str(e),
            service_obj=service_obj,
        )


def _execute_service_targets_parallel(
    target_ips: List[tuple],
    service_name: str,
    action: str,
    timeout: Optional[int] = None,
    status_ctx=None,
) -> Tuple[List[dict], List[dict]]:
    """Execute a service action across targets in parallel."""
    results: List[dict] = []
    failures: List[dict] = []
    total = len(target_ips)

    def _on_complete(done: int, total: int) -> None:
        if status_ctx is not None:
            status_ctx.update(
                f"[bold blue]{action.capitalize()} [{done}/{total} targets]...[/bold blue]"
            )

    def worker(target: Tuple[Any, str]) -> Tuple[Optional[dict], Optional[dict]]:
        return _execute_service_target(target, service_name, action, timeout=timeout)

    for result, failure in parallel_map_ordered(
        target_ips, worker, on_complete=_on_complete if status_ctx else None
    ):
        if result:
            results.append(result)
        if failure:
            failures.append(failure)

    return results, failures


def _build_target_service_index(servers) -> Dict[Tuple[str, str], List[Service]]:
    """Map each target server/ip pair to its services."""
    target_service_map: Dict[Tuple[str, str], List[Service]] = {}
    for server_obj in servers:
        for server_ip in server_obj.ips:
            target_service_map[(server_obj.name, server_ip)] = list(server_obj.services)
    return target_service_map


def _execute_all_services_for_target(
    target: Tuple[Any, str],
    action: str,
    services_by_target: Dict[Tuple[str, str], List[Service]],
    timeout: Optional[int] = None,
) -> Tuple[List[dict], List[dict]]:
    """Execute an action for all services on one target, sequentially per target."""
    server_obj, server_ip = target
    target_key = (server_obj.name, server_ip)
    results: List[dict] = []
    failures: List[dict] = []

    for service_obj in services_by_target.get(target_key, []):
        result, failure = _execute_service_target(
            (server_obj, server_ip),
            service_obj.name,
            action,
            timeout=timeout,
        )
        if result:
            results.append(result)
        if failure:
            failures.append(failure)

    return results, failures


def _execute_all_services_parallel(
    target_ips: List[tuple],
    action: str,
    services_by_target: Dict[Tuple[str, str], List[Service]],
    timeout: Optional[int] = None,
) -> Tuple[List[dict], List[dict]]:
    """Execute an action for all services, parallelizing by target."""
    all_results: List[dict] = []
    all_failures: List[dict] = []

    def worker(target: Tuple[Any, str]) -> Tuple[List[dict], List[dict]]:
        return _execute_all_services_for_target(
            target,
            action,
            services_by_target,
            timeout=timeout,
        )

    for target_results, target_failures in parallel_map_ordered(target_ips, worker):
        all_results.extend(target_results)
        all_failures.extend(target_failures)

    return all_results, all_failures


def _apply_monitor_change_highlights(results: List[dict], previous_values: dict) -> tuple[List[dict], dict]:
    """Highlight changed fields between monitor refresh cycles."""
    highlighted_results: List[dict] = []
    current_values: dict = {}
    track_fields = ["status", "pid", "cpu", "ram", "since"]

    for result in results:
        row = dict(result)
        key = _result_key(result)
        snapshot = {field: str(result.get(field, "")) for field in track_fields}
        current_values[key] = snapshot
        prev_snapshot = previous_values.get(key)

        if prev_snapshot:
            for field in track_fields:
                old = prev_snapshot.get(field, "")
                new = snapshot[field]
                if new != old:
                    if field == "status":
                        row["_status_changed"] = True
                    else:
                        row[field] = f"[bold bright_yellow]{result.get(field, '')}[/bold bright_yellow]"

        highlighted_results.append(row)

    return highlighted_results, current_values


def _build_status_command_with_metrics(service_obj: Service, server_type: str = "", use_sudo: bool = False) -> str:
    """Build status command with runtime metrics for supported service types."""
    os_type = (server_type or "").strip().lower()
    is_centos_like = "centos" in os_type or "rhel" in os_type or "rocky" in os_type or "alma" in os_type

    if service_obj.type == "systemd":
        service_name = shlex.quote(service_obj.name)
        if is_centos_like:
            load_state_expr = f"systemctl show -p LoadState {service_name} 2>/dev/null | sed 's/^LoadState=//' | tr -d '\\r' | xargs"
            since_expr = f"systemctl show -p ActiveEnterTimestamp {service_name} 2>/dev/null | sed 's/^ActiveEnterTimestamp=//' | xargs"
            main_pid_expr = f"systemctl show -p MainPID {service_name} 2>/dev/null | sed 's/^MainPID=//' | tr -d '\\r'"
            main_pid_fallback_expr = f"systemctl show -p ExecMainPID {service_name} 2>/dev/null | sed 's/^ExecMainPID=//' | tr -d '\\r'"
        else:
            load_state_expr = f"systemctl show -p LoadState --value {service_name} 2>/dev/null | tr -d '\\r' | xargs"
            since_expr = f"systemctl show -p ActiveEnterTimestamp --value {service_name} 2>/dev/null | xargs"
            main_pid_expr = f"systemctl show -p MainPID --value {service_name} 2>/dev/null | tr -d '\\r'"
            main_pid_fallback_expr = f"systemctl show -p ExecMainPID --value {service_name} 2>/dev/null | tr -d '\\r'"

        base_command = (
            f"LOAD_STATE=$({load_state_expr}); "
            "if [ \"$LOAD_STATE\" = \"not-found\" ]; then echo \"DAGDI_STATUS=NOT_FOUND\"; fi; "
            f"SINCE=$({since_expr}); "
            "if [ -n \"$SINCE\" ] && [ \"$SINCE\" != \"n/a\" ]; then echo \"DAGDI_SINCE=$SINCE\"; fi; "
            f"MAINPID=$({main_pid_expr}); "
            f"if [ -z \"$MAINPID\" ] || [ \"$MAINPID\" = \"0\" ]; then MAINPID=$({main_pid_fallback_expr}); fi; "
            f"CONTROL_GROUP=$(systemctl show -p ControlGroup --value {service_name} 2>/dev/null | tr -d '\\r' | xargs); "
            "CGROUP_PATH=''; "
            "if [ -n \"$CONTROL_GROUP\" ] && [ \"$CONTROL_GROUP\" != \"/\" ]; then "
            "if [ -d \"/sys/fs/cgroup$CONTROL_GROUP\" ]; then CGROUP_PATH=\"/sys/fs/cgroup$CONTROL_GROUP\"; "
            "elif [ -d \"/sys/fs/cgroup/systemd$CONTROL_GROUP\" ]; then CGROUP_PATH=\"/sys/fs/cgroup/systemd$CONTROL_GROUP\"; "
            "elif [ -d \"/sys/fs/cgroup/memory$CONTROL_GROUP\" ]; then CGROUP_PATH=\"/sys/fs/cgroup/memory$CONTROL_GROUP\"; "
            "fi; "
            "fi; "
            "MEM_BYTES=''; "
            "PROC_FILE=''; "
            "TOTAL_CPU=''; "
            "TOTAL_RSS_KB=''; "
            "if [ -n \"$CGROUP_PATH\" ]; then "
            "if [ -r \"$CGROUP_PATH/memory.current\" ]; then MEM_BYTES=$(tr -d '\\r' < \"$CGROUP_PATH/memory.current\"); "
            "elif [ -r \"$CGROUP_PATH/memory.usage_in_bytes\" ]; then MEM_BYTES=$(tr -d '\\r' < \"$CGROUP_PATH/memory.usage_in_bytes\"); "
            "fi; "
            "if [ -r \"$CGROUP_PATH/cgroup.procs\" ]; then PROC_FILE=\"$CGROUP_PATH/cgroup.procs\"; "
            "elif [ -r \"$CGROUP_PATH/tasks\" ]; then PROC_FILE=\"$CGROUP_PATH/tasks\"; "
            "fi; "
            "if [ -n \"$PROC_FILE\" ]; then "
            "PIDS=$(tr '\\n' ',' < \"$PROC_FILE\" | sed 's/,$//'); "
            "if [ -n \"$PIDS\" ]; then "
            "PS_LINES=$(ps -o %cpu=,rss= -p \"$PIDS\" 2>/dev/null); "
            "if [ -n \"$PS_LINES\" ]; then "
            "TOTAL_CPU=$(echo \"$PS_LINES\" | awk '{cpu+=$1} END {if (NR>0) printf \"%.1f\", cpu}'); "
            "TOTAL_RSS_KB=$(echo \"$PS_LINES\" | awk '{rss+=$2} END {if (NR>0) printf \"%.0f\", rss}'); "
            "fi; "
            "fi; "
            "fi; "
            "fi; "
            "if [ -n \"$MAINPID\" ] && [ \"$MAINPID\" != \"0\" ]; then "
            "echo \"DAGDI_PID=$MAINPID\"; "
            "else "
            "echo \"DAGDI_PID=-\"; "
            "fi; "
            "if [ -z \"$TOTAL_CPU\" ] || [ -z \"$TOTAL_RSS_KB\" ]; then "
            "if [ -n \"$MAINPID\" ] && [ \"$MAINPID\" != \"0\" ]; then "
            "PS_LINE=$(ps -p \"$MAINPID\" -o %cpu=,rss= 2>/dev/null); "
            "if [ -n \"$PS_LINE\" ]; then "
            "if [ -z \"$TOTAL_CPU\" ]; then TOTAL_CPU=$(echo \"$PS_LINE\" | awk '{print $1}'); fi; "
            "if [ -z \"$TOTAL_RSS_KB\" ]; then TOTAL_RSS_KB=$(echo \"$PS_LINE\" | awk '{print $2}'); fi; "
            "fi; "
            "fi; "
            "fi; "
            "if [ -n \"$TOTAL_CPU\" ]; then echo \"DAGDI_CPU=${TOTAL_CPU}%\"; fi; "
            "if [ -n \"$MEM_BYTES\" ] && echo \"$MEM_BYTES\" | grep -Eq '^[0-9]+$' && [ \"$MEM_BYTES\" != \"18446744073709551615\" ]; then "
            "echo \"DAGDI_RAM_BYTES=$MEM_BYTES\"; "
            "elif [ -n \"$TOTAL_RSS_KB\" ]; then "
            "RSS_BYTES=$(awk \"BEGIN {printf \\\"%.0f\\\", $TOTAL_RSS_KB*1024}\"); "
            "echo \"DAGDI_RAM_BYTES=$RSS_BYTES\"; "
            "fi; "
            f"systemctl status {service_name} --no-pager 2>/dev/null"
        )
        if use_sudo:
            return f"sudo sh -c {shlex.quote(base_command)}"
        return base_command

    if service_obj.type == "docker":
        container_name = service_obj.config.get("container_name", service_obj.name)
        container_name = shlex.quote(container_name)
        docker_script = (
            f"STATE=$(docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null | head -n 1 | tr -d '\\r' | xargs); "
            "if [ -z \"$STATE\" ]; then "
            "echo \"DAGDI_STATUS=NOT_FOUND\"; "
            "else "
            "echo \"DAGDI_DOCKER_STATE=$STATE\"; "
            f"SINCE=$(docker inspect -f '{{{{.State.StartedAt}}}}' {container_name} 2>/dev/null | head -n 1); "
            "if [ -n \"$SINCE\" ] && [ \"$SINCE\" != \"0001-01-01T00:00:00Z\" ]; then echo \"DAGDI_SINCE=$SINCE\"; fi; "
            "if [ \"$STATE\" = \"running\" ]; then "
            f"STATS=$(docker stats --no-stream --format '{{{{.CPUPerc}}}}|{{{{.MemUsage}}}}' {container_name} 2>/dev/null | head -n 1); "
            "if [ -n \"$STATS\" ]; then "
            "CPU=$(echo \"$STATS\" | cut -d'|' -f1); "
            "MEM=$(echo \"$STATS\" | cut -d'|' -f2 | cut -d'/' -f1 | xargs); "
            "echo \"DAGDI_CPU=$CPU\"; "
            "echo \"DAGDI_RAM=$MEM\"; "
            "fi; "
            "fi; "
            "fi"
        )
        if use_sudo:
            # Docker status uses command substitutions and shell conditionals;
            # run the whole script as root to avoid false NOT_FOUND markers.
            return f"sudo sh -c {shlex.quote(docker_script)}"
        return docker_script

    command = CommandBuilder.get_status_command(service_obj)
    return f"sudo {command}" if use_sudo else command


def _parse_service_metrics(result: ExecutionResult, service_type: str) -> dict:
    """Parse PID/CPU/RAM metrics from status output."""
    metrics = {
        "pid": "-",
        "cpu": "N/A",
        "ram": "N/A",
        "since": "N/A",
    }

    if result.error:
        return metrics

    for line in result.stdout.splitlines():
        if line.startswith("DAGDI_PID="):
            metrics["pid"] = line.split("=", 1)[1].strip() or "-"
        elif line.startswith("DAGDI_CPU="):
            metrics["cpu"] = line.split("=", 1)[1].strip() or "N/A"
        elif line.startswith("DAGDI_RAM_BYTES="):
            raw_value = line.split("=", 1)[1].strip()
            metrics["ram"] = _format_memory_bytes(raw_value)
        elif line.startswith("DAGDI_RAM="):
            metrics["ram"] = line.split("=", 1)[1].strip() or "N/A"
        elif line.startswith("DAGDI_SINCE="):
            metrics["since"] = line.split("=", 1)[1].strip() or "N/A"

    if service_type != "systemd":
        metrics["pid"] = "-"

    return metrics


def _format_memory_bytes(raw_value: str) -> str:
    """Format a raw byte count into a human-readable value."""
    if not raw_value:
        return "N/A"

    try:
        byte_count = int(raw_value)
    except ValueError:
        return "N/A"

    if byte_count < 0:
        return "N/A"
    if byte_count == 0:
        return "0.0MB"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(byte_count)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(value)}B"

    return f"{value:.1f}{units[unit_index]}"


def _parse_service_status(result: ExecutionResult, service_type: str) -> str:
    """
    Parse service status from command output.
    
    Args:
        result: ExecutionResult from status command
        service_type: Type of service (systemd, docker)
    
    Returns:
        Status string: RUNNING, STOPPED, FAILED, or UNKNOWN
    """
    if result.error:
        return "UNKNOWN"

    output = result.stdout.lower()

    if service_type == "systemd":
        if "dagdi_status=not_found" in output or "could not be found" in output:
            return "NOT_FOUND"
        if "loaded: not-found" in output:
            return "NOT_FOUND"
    elif service_type == "docker":
        if "dagdi_status=not_found" in output:
            return "NOT_FOUND"
        for line in result.stdout.splitlines():
            if line.startswith("DAGDI_DOCKER_STATE="):
                state = line.split("=", 1)[1].strip().lower()
                if state in {"running", "restarting"}:
                    return "RUNNING"
                if state in {"exited", "dead", "created", "paused", "removing"}:
                    return "STOPPED"
                return "UNKNOWN"

    if result.return_code != 0:
        # Non-zero for systemd can be many things; if output is empty, don't
        # assume STOPPED because the unit may be missing or inaccessible.
        if service_type == "systemd" and not output.strip():
            return "UNKNOWN"
        return "STOPPED"
    
    if service_type == "systemd":
        if "active (running)" in output:
            return "RUNNING"
        elif "active: failed" in output or "failed" in output:
            return "FAILED"
        elif "inactive (dead)" in output:
            return "STOPPED"
        else:
            return "UNKNOWN"
    elif service_type == "docker":
        if "up" in output:
            return "RUNNING"
        elif "exited" in output or "dead" in output:
            return "STOPPED"
        else:
            return "UNKNOWN"
    else:
        return "UNKNOWN"


@service_app.command()
def service(
    name: str = typer.Argument(..., help="Service name"),
    action: str = typer.Argument(..., help="Action: status, start, stop, restart"),
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
        False, "--monitor", help="Continuously refresh status table (status action only)"
    ),
    on_failure: Optional[str] = typer.Option(
        None, "--on-failure", help="Behavior on partial failure: continue|stop|prompt"
    ),
) -> None:
    """Manage services: status, start, stop, restart.

    Examples:
        dagdi manage service nginx status              # Check status
        dagdi manage service nginx start               # Start service
        dagdi manage service nginx stop                # Stop service
        dagdi manage service nginx restart             # Restart service
        dagdi manage service nginx start --server web-1  # On specific server
        dagdi manage service nginx stop --ip 10.0.1.10   # On specific IP
    """
    _execute_service_action(
        name=name,
        action=action,
        product=product,
        environment=environment,
        server=server,
        ip=ip,
        timeout=timeout,
        monitor=monitor,
        on_failure=on_failure,
    )


def _execute_service_action(
    name: str,
    action: str,
    product: Optional[str] = None,
    environment: Optional[str] = None,
    server: Optional[str] = None,
    ip: Optional[str] = None,
    timeout: Optional[int] = None,
    monitor: bool = False,
    on_failure: Optional[str] = None,
) -> None:
    """Internal function to execute service actions."""
    try:
        # Validate action
        valid_actions = ["status", "start", "stop", "restart"]
        if action not in valid_actions:
            typer.echo(
                f"Error: Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}",
                err=True
            )
            raise typer.Exit(1)

        if monitor and action != "status":
            typer.echo("Error: --monitor can only be used with the 'status' action", err=True)
            raise typer.Exit(1)

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
            service=name,
        )

        # Get target servers and IPs
        target_ips = get_target_ips(scope.servers)

        if not target_ips:
            typer.echo("No servers found matching the specified scope.")
            raise typer.Exit(1)

        if action == "status" and monitor:
            from rich.live import Live

            _preflight_monitor_auth(target_ips)
            results, _ = _execute_service_targets_parallel(
                target_ips, name, "status", timeout=timeout,
            )
            previous_values: dict = {}
            display_results, previous_values = _apply_monitor_change_highlights(results, previous_values)
            live = Live(
                _build_status_table("Service Status (Monitoring)", display_results),
                refresh_per_second=4,
            )
            live.start()
            try:
                while True:
                    _interruptible_sleep(2)
                    results, _ = _execute_service_targets_parallel(
                        target_ips, name, "status", timeout=timeout,
                    )
                    display_results, previous_values = _apply_monitor_change_highlights(results, previous_values)
                    live.update(_build_status_table("Service Status (Monitoring)", display_results))
            except KeyboardInterrupt:
                pass
            finally:
                live.stop()
            return

        # Confirm destructive actions
        if action in ["stop", "restart"]:
            typer.echo(f"⚠️  About to {action} service '{name}' on {len(target_ips)} target(s)")
            if not typer.confirm("Continue?"):
                typer.echo("Cancelled.")
                raise typer.Exit(0)

        # Resolve credentials before any live/spinner display
        _preflight_monitor_auth(target_ips)

        # Execute action on all targets
        results = []
        failures = []
        status_live = None
        live_status_enabled = action == "status" and config.global_settings.live_status_table

        if live_status_enabled:
            from rich.live import Live
            status_live = Live(
                _build_status_table("Service Status", results),
                refresh_per_second=6,
                transient=False,
            )
            status_live.start()

        try:
            if live_status_enabled:
                results, failures = _execute_service_targets_parallel(
                    target_ips, name, action, timeout=timeout,
                )
                status_live.update(_build_status_table("Service Status", results))
            else:
                total = len(target_ips)
                with _progress_console.status(
                    f"[bold blue]{action.capitalize()} [0/{total} targets]...[/bold blue]",
                    spinner="dots",
                ) as spin:
                    results, failures = _execute_service_targets_parallel(
                        target_ips, name, action, timeout=timeout, status_ctx=spin,
                    )
        finally:
            if status_live:
                status_live.stop()

        # Display results
        formatter = Formatter()
        
        if action == "status":
            # Render statically unless live table is enabled.
            if not live_status_enabled:
                _display_status_results(results)
        else:
            # Display action results
            _display_action_results(results, action)

        # Display summary
        if failures:
            typer.echo(f"\n⚠️  {len(failures)} target(s) failed:")
            for failure in failures:
                typer.echo(f"  [{failure['server']} | {failure['ip']}] {failure['error']}")

        # Display success summary
        success_count = len([r for r in results if r.get("success", False)])
        typer.echo(
            f"\n✓ {action.capitalize()} completed on {success_count} target(s), {len(failures)} failed"
        )

        if failures and len(failures) == len(results) + len(failures):
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


def _display_status_results(results: List[dict]) -> None:
    """Display service status results in table format."""
    from rich.console import Console

    console = Console()
    console.print(_build_status_table("Service Status", results))


def _display_action_results(results: List[dict], action: str) -> None:
    """Display service action results in table format."""
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=f"Service {action.capitalize()}", box=box.ROUNDED, show_lines=True)
    table.add_column("Server", style="cyan")
    table.add_column("Service", style="green")
    table.add_column("Result", style="yellow")

    sorted_results = _sort_results_by_server(results)
    prev_server_key = None

    for result in sorted_results:
        server_key = f"{result['server']}|{result['ip']}"
        if server_key != prev_server_key:
            server_label = f"{result['server']} ({result['ip']})"
            prev_server_key = server_key
        else:
            server_label = ""

        success = result["success"]
        result_text = "SUCCESS" if success else "FAILED"
        result_style = "green" if success else "red"
        table.add_row(
            server_label,
            result["service"],
            f"[{result_style}]{result_text}[/{result_style}]",
        )

    console.print(table)


def _display_consolidated_status(results: List[dict]) -> None:
    """Display all service statuses in a single consolidated table."""
    from rich.console import Console

    console = Console()
    console.print(_build_status_table("All Services Status", results))


def _sort_results_by_server(results: List[dict]) -> List[dict]:
    """Sort results by server name, preserving service order within each server."""
    return sorted(results, key=lambda r: r.get("server", ""))


def _build_status_table(title: str, results: List[dict]):
    """Build a status table for static or live rendering."""
    from rich import box
    from rich.table import Table

    table = Table(title=title, box=box.ROUNDED, show_lines=True)
    table.add_column("Server", style="cyan")
    table.add_column("Service", style="green")
    table.add_column("Type", style="blue")
    table.add_column("PID", style="cyan")
    table.add_column("CPU", style="magenta")
    table.add_column("RAM", style="magenta")
    table.add_column("Since", style="blue")
    table.add_column("Status")

    sorted_results = _sort_results_by_server(results)
    prev_server_key = None

    for result in sorted_results:
        server_key = f"{result['server']}|{result['ip']}"
        if server_key != prev_server_key:
            server_label = f"{result['server']} ({result['ip']})"
            prev_server_key = server_key
        else:
            server_label = ""

        status = result["status"]
        status_text = format_status_indicator(status)
        if result.get("_status_changed"):
            status_text = f"[bold]{status_text}[/bold]"

        cpu_val = result.get("cpu", "N/A")
        ram_val = result.get("ram", "N/A")
        if cpu_val in ("N/A", "-", ""):
            cpu_display = f"[dim]{cpu_val}[/dim]"
        else:
            cpu_display = str(cpu_val)
        if ram_val in ("N/A", "-", ""):
            ram_display = f"[dim]{ram_val}[/dim]"
        else:
            ram_display = str(ram_val)

        table.add_row(
            server_label,
            result["service"],
            result.get("service_type", "UNKNOWN"),
            result.get("pid", "-"),
            cpu_display,
            ram_display,
            result.get("since", "N/A"),
            status_text,
        )

    return table


def _display_consolidated_action(results: List[dict], action: str) -> None:
    """Display all service action results in a single consolidated table."""
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=f"All Services {action.capitalize()}", box=box.ROUNDED, show_lines=True)
    table.add_column("Server", style="cyan")
    table.add_column("Service", style="green")
    table.add_column("Result", style="yellow")

    sorted_results = _sort_results_by_server(results)
    prev_server_key = None

    for result in sorted_results:
        server_key = f"{result['server']}|{result['ip']}"
        if server_key != prev_server_key:
            server_label = f"{result['server']} ({result['ip']})"
            prev_server_key = server_key
        else:
            server_label = ""

        success = result["success"]
        result_text = "SUCCESS" if success else "FAILED"
        result_style = "green" if success else "red"
        table.add_row(
            server_label,
            result["service"],
            f"[{result_style}]{result_text}[/{result_style}]",
        )

    console.print(table)



def manage_single_service(
    service_name: str = typer.Argument(..., help="Service name"),
    action: str = typer.Argument(..., help="Action: status, start, stop, restart"),
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
        False, "--monitor", help="Continuously refresh status table (status action only)"
    ),
    on_failure: Optional[str] = typer.Option(
        None, "--on-failure", help="Behavior on partial failure: continue|stop|prompt"
    ),
) -> None:
    """Shortcut for managing a single service.
    
    Equivalent to: dagdi manage service <name> <action>
    
    Examples:
        dagdi ms nginx status
        dagdi ms nginx start
        dagdi ms nginx stop
        dagdi ms nginx restart
    """
    # Delegate to the internal function
    _execute_service_action(
        name=service_name,
        action=action,
        product=product,
        environment=environment,
        server=server,
        ip=ip,
        timeout=timeout,
        monitor=monitor,
        on_failure=on_failure,
    )


def manage_multiple_services(
    services_and_action: List[str] = typer.Argument(..., help="Service names followed by action"),
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
        False, "--monitor", help="Continuously refresh status table (status action only)"
    ),
    on_failure: Optional[str] = typer.Option(
        None, "--on-failure", help="Behavior on partial failure: continue|stop|prompt"
    ),
) -> None:
    """Shortcut for managing multiple services.
    
    The last argument is the action, all preceding arguments are service names.
    
    Examples:
        dagdi mss nginx api postgres restart
        dagdi mss nginx api stop
        dagdi mss nginx postgres start
    """
    if len(services_and_action) < 2:
        typer.echo("Error: Must provide at least one service name and an action", err=True)
        raise typer.Exit(1)
    
    # Last argument is the action
    action = services_and_action[-1]
    service_names = services_and_action[:-1]

    if monitor and action != "status":
        typer.echo("Error: --monitor can only be used with the 'status' action", err=True)
        raise typer.Exit(1)
    if monitor and len(service_names) > 1:
        typer.echo("Error: --monitor with mss supports one service at a time", err=True)
        raise typer.Exit(1)
    
    # Validate action
    valid_actions = ["status", "start", "stop", "restart"]
    if action not in valid_actions:
        typer.echo(
            f"Error: Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}",
            err=True
        )
        raise typer.Exit(1)
    
    # Execute action for each service
    for service_name in service_names:
        typer.echo(f"\n{'='*60}")
        typer.echo(f"Managing service: {service_name}")
        typer.echo(f"{'='*60}")
        
        _execute_service_action(
            name=service_name,
            action=action,
            product=product,
            environment=environment,
            server=server,
            ip=ip,
            timeout=timeout,
            monitor=monitor,
            on_failure=on_failure,
        )


def manage_all_services(
    action: str = typer.Argument(..., help="Action: status, start, stop, restart"),
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
        False, "--monitor", help="Continuously refresh status table (status action only)"
    ),
    on_failure: Optional[str] = typer.Option(
        None, "--on-failure", help="Behavior on partial failure: continue|stop|prompt"
    ),
) -> None:
    """Shortcut for managing all services in an environment.
    
    Examples:
        dagdi mas status
        dagdi mas start
        dagdi mas stop
        dagdi mas restart
    """
    try:
        # Validate action
        valid_actions = ["status", "start", "stop", "restart"]
        if action not in valid_actions:
            typer.echo(
                f"Error: Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}",
                err=True
            )
            raise typer.Exit(1)

        if monitor and action != "status":
            typer.echo("Error: --monitor can only be used with the 'status' action", err=True)
            raise typer.Exit(1)

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

        # Get all unique service names from target servers
        service_names = set()
        for server_obj in scope.servers:
            for svc in server_obj.services:
                service_names.add(svc.name)

        if not service_names:
            typer.echo("No services found in the specified scope.")
            raise typer.Exit(1)

        if action == "status" and monitor:
            target_ips = get_target_ips(scope.servers)
            services_by_target = _build_target_service_index(scope.servers)
            from rich.live import Live

            _preflight_monitor_auth(target_ips)
            all_results, _ = _execute_all_services_parallel(
                target_ips, "status", services_by_target, timeout=timeout,
            )
            previous_values: dict = {}
            display_results, previous_values = _apply_monitor_change_highlights(all_results, previous_values)
            live = Live(
                _build_status_table("All Services Status (Monitoring)", display_results),
                refresh_per_second=4,
            )
            live.start()
            try:
                while True:
                    _interruptible_sleep(2)
                    all_results, _ = _execute_all_services_parallel(
                        target_ips, "status", services_by_target, timeout=timeout,
                    )
                    display_results, previous_values = _apply_monitor_change_highlights(all_results, previous_values)
                    live.update(_build_status_table("All Services Status (Monitoring)", display_results))
            except KeyboardInterrupt:
                pass
            finally:
                live.stop()
            return

        # Confirm destructive actions
        if action in ["stop", "restart"]:
            typer.echo(f"⚠️  About to {action} {len(service_names)} service(s) on {len(scope.servers)} server(s)")
            if not typer.confirm("Continue?"):
                typer.echo("Cancelled.")
                raise typer.Exit(0)

        # Resolve credentials before any live/spinner display
        target_ips = get_target_ips(scope.servers)
        _preflight_monitor_auth(target_ips)

        # Collect all results in a single list
        all_results = []
        all_failures = []
        consolidated_status_live = None
        live_status_enabled = action == "status" and config.global_settings.live_status_table

        if live_status_enabled:
            from rich.live import Live
            consolidated_status_live = Live(
                _build_status_table("All Services Status", all_results),
                refresh_per_second=6,
                transient=False,
            )
            consolidated_status_live.start()

        try:
            services_by_target = _build_target_service_index(scope.servers)
            if live_status_enabled:
                all_results, all_failures = _execute_all_services_parallel(
                    target_ips, action, services_by_target, timeout=timeout,
                )
                consolidated_status_live.update(
                    _build_status_table("All Services Status", all_results)
                )
            else:
                with _progress_console.status(
                    f"[bold blue]{action.capitalize()} all services "
                    f"on {len(target_ips)} target(s)...[/bold blue]",
                    spinner="dots",
                ):
                    all_results, all_failures = _execute_all_services_parallel(
                        target_ips, action, services_by_target, timeout=timeout,
                    )
        finally:
            if consolidated_status_live:
                consolidated_status_live.stop()

        # Display consolidated results in a single table
        if action == "status":
            # Render statically unless live table is enabled.
            if not live_status_enabled:
                _display_consolidated_status(all_results)
        else:
            _display_consolidated_action(all_results, action)

        # Display summary
        if all_failures:
            typer.echo(f"\n⚠️  {len(all_failures)} target(s) failed:")
            for failure in all_failures:
                typer.echo(f"  [{failure['server']} | {failure['ip']} | {failure['service']}] {failure['error']}")

        # Display success summary
        success_count = len([r for r in all_results if r.get("success", False)])
        typer.echo(
            f"\n✓ {action.capitalize()} completed on {len(all_results)} target(s), {len(all_failures)} failed"
        )

        if all_failures and len(all_failures) == len(all_results) + len(all_failures):
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


# Register shortcut commands under the manage command group as well.
service_app.command(name="ms", help="Manage single service")(manage_single_service)
service_app.command(name="mss", help="Manage multiple services")(manage_multiple_services)
service_app.command(name="mas", help="Manage all services")(manage_all_services)
