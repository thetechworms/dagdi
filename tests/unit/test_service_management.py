"""Unit tests for service management commands."""

import threading
import time
import pytest
from unittest.mock import Mock, patch
from src.dagdi.commands.service_management import (
    service, _parse_service_status, _parse_service_metrics, _display_status_results, _display_action_results, _display_consolidated_status, _build_status_command_with_metrics, _format_memory_bytes
)
from src.dagdi.models import (
    Configuration, Product, Environment, Server, Service, SSHConfig, Context, ExecutionResult
)


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
    
    service1 = Service(name="nginx", type="systemd")
    service2 = Service(name="api", type="docker", config={"container_name": "api-container"})
    
    server1 = Server(
        name="web-1",
        type="ubuntu",
        ips=["10.0.1.10", "10.0.1.11"],
        ssh_config=ssh_config,
        services=[service1, service2]
    )
    
    service3 = Service(name="postgres", type="systemd")
    server2 = Server(
        name="db-1",
        type="ubuntu",
        ips=["10.0.2.10"],
        ssh_config=ssh_config,
        services=[service3]
    )
    
    env_dev = Environment(name="dev", servers=[server1, server2])
    env_prod = Environment(name="prod", servers=[server1])
    
    product1 = Product(name="myapp", environments=[env_dev, env_prod])
    
    return Configuration(products=[product1])


@pytest.fixture
def sample_context():
    """Create a sample context for testing."""
    return Context(product="myapp", environment="dev")


class TestParseServiceStatus:
    """Tests for _parse_service_status function."""

    def test_parse_systemd_running(self):
        """Test parsing systemd service as running."""
        result = ExecutionResult(
            stdout="● nginx.service - Nginx HTTP Server\n   Loaded: loaded (/etc/systemd/system/nginx.service; enabled)\n   Active: active (running) since Mon 2024-01-15 10:00:00 UTC; 1h ago\n",
            return_code=0
        )
        status = _parse_service_status(result, "systemd")
        assert status == "RUNNING"

    def test_parse_systemd_stopped(self):
        """Test parsing systemd service as stopped."""
        result = ExecutionResult(
            stdout="● nginx.service - Nginx HTTP Server\n   Loaded: loaded (/etc/systemd/system/nginx.service; disabled)\n   Active: inactive (dead)\n",
            return_code=0
        )
        status = _parse_service_status(result, "systemd")
        assert status == "STOPPED"

    def test_parse_docker_running(self):
        """Test parsing docker service as running."""
        result = ExecutionResult(
            stdout="Up 2 hours\n",
            return_code=0
        )
        status = _parse_service_status(result, "docker")
        assert status == "RUNNING"

    def test_parse_docker_stopped(self):
        """Test parsing docker service as stopped."""
        result = ExecutionResult(
            stdout="Exited (0) 1 hour ago\n",
            return_code=0
        )
        status = _parse_service_status(result, "docker")
        assert status == "STOPPED"

    def test_parse_docker_state_marker_running(self):
        """Should classify docker running state from explicit marker."""
        result = ExecutionResult(
            stdout="DAGDI_DOCKER_STATE=running\n",
            return_code=0,
        )
        status = _parse_service_status(result, "docker")
        assert status == "RUNNING"

    def test_parse_docker_not_found_from_marker(self):
        """Should classify missing docker container as NOT_FOUND."""
        result = ExecutionResult(
            stdout="DAGDI_STATUS=NOT_FOUND\n",
            return_code=0,
        )
        status = _parse_service_status(result, "docker")
        assert status == "NOT_FOUND"

    def test_parse_status_with_error(self):
        """Test parsing status when command has error."""
        result = ExecutionResult(error="SSH connection failed")
        status = _parse_service_status(result, "systemd")
        assert status == "UNKNOWN"


class TestParseServiceMetrics:
    """Tests for _parse_service_metrics helpers."""

    def test_parse_systemd_metrics_prefers_raw_bytes_marker(self):
        """Should convert raw byte output to a human-readable RAM value."""
        result = ExecutionResult(
            stdout="DAGDI_PID=123\nDAGDI_CPU=12.5%\nDAGDI_RAM_BYTES=10737418240\nDAGDI_SINCE=Mon 2024-01-15 10:00:00 UTC\n",
            return_code=0,
        )

        metrics = _parse_service_metrics(result, "systemd")

        assert metrics["pid"] == "123"
        assert metrics["cpu"] == "12.5%"
        assert metrics["ram"] == "10.0GB"
        assert metrics["since"] == "Mon 2024-01-15 10:00:00 UTC"

    def test_parse_non_systemd_metrics_keeps_pid_hidden(self):
        """Non-systemd services should not expose PID in status table."""
        result = ExecutionResult(
            stdout="DAGDI_PID=321\nDAGDI_CPU=1.0%\nDAGDI_RAM=256.0MB\n",
            return_code=0,
        )

        metrics = _parse_service_metrics(result, "docker")

        assert metrics["pid"] == "-"
        assert metrics["cpu"] == "1.0%"
        assert metrics["ram"] == "256.0MB"


class TestMemoryFormatting:
    """Tests for memory formatting helper."""

    def test_format_memory_bytes_large_value(self):
        """Large byte counts should be shown in GB."""
        assert _format_memory_bytes("10737418240") == "10.0GB"

    def test_format_memory_bytes_invalid_value(self):
        """Invalid memory data should not crash parsing."""
        assert _format_memory_bytes("not-a-number") == "N/A"

    def test_parse_status_with_nonzero_return_code(self):
        """Test parsing status when return code is non-zero."""
        result = ExecutionResult(
            stdout="",
            return_code=1
        )
        status = _parse_service_status(result, "systemd")
        assert status == "UNKNOWN"

    def test_parse_systemd_not_found_from_marker(self):
        """Should classify missing systemd unit as NOT_FOUND."""
        result = ExecutionResult(
            stdout="DAGDI_STATUS=NOT_FOUND\n",
            return_code=4,
        )
        status = _parse_service_status(result, "systemd")
        assert status == "NOT_FOUND"

    def test_parse_systemd_not_found_from_text(self):
        """Should classify missing systemd unit using systemctl text."""
        result = ExecutionResult(
            stdout="Unit xyz.service could not be found.\n",
            return_code=4,
        )
        status = _parse_service_status(result, "systemd")
        assert status == "NOT_FOUND"

    def test_parse_status_unknown_output(self):
        """Test parsing status with unknown output."""
        result = ExecutionResult(
            stdout="Some unknown output\n",
            return_code=0
        )
        status = _parse_service_status(result, "systemd")
        assert status == "UNKNOWN"


class TestServiceCommand:
    """Tests for service command."""

    def test_service_command_imports(self):
        """Test that service command can be imported."""
        # Just test that the module can be imported
        import src.dagdi.commands.service_management
        assert src.dagdi.commands.service_management is not None



class TestServiceShortcuts:
    """Tests for service management shortcuts."""

    def test_ms_shortcut_imports(self):
        """Test that ms shortcut can be imported."""
        import src.dagdi.commands.service_management
        assert src.dagdi.commands.service_management is not None

    def test_mss_shortcut_imports(self):
        """Test that mss shortcut can be imported."""
        import src.dagdi.commands.service_management
        assert src.dagdi.commands.service_management is not None

    def test_mas_shortcut_imports(self):
        """Test that mas shortcut can be imported."""
        import src.dagdi.commands.service_management
        assert src.dagdi.commands.service_management is not None

    def test_mss_requires_at_least_two_args(self):
        """Test that mss requires at least service name and action."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()
        result = runner.invoke(service_app, ["mss", "nginx"])

        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "Must provide at least one service name and an action" in output or result.exit_code == 1

    def test_mss_invalid_action(self):
        """Test that mss rejects invalid action."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()
        result = runner.invoke(service_app, ["mss", "nginx", "api", "invalid_action"])

        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "Invalid action" in output or result.exit_code == 1

    def test_mss_monitor_requires_status_action(self):
        """Test that --monitor is rejected for non-status actions."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()
        result = runner.invoke(service_app, ["mss", "nginx", "restart", "--monitor"])

        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "--monitor can only be used with the 'status' action" in output

    def test_mas_monitor_prepares_sudo_before_live_rendering(self, sample_config):
        """Should preflight sudo auth before entering monitor/live refresh."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()
        fake_scope = Mock()
        sudo_server = sample_config.products[0].environments[0].servers[0]
        sudo_server.ssh_config.sudo = True
        fake_scope.servers = [sudo_server]

        class FakeLive:
            def __init__(self, *args, **kwargs):
                self.started = False
                self.stopped = False

            def start(self):
                self.started = True

            def update(self, _renderable):
                pass

            def stop(self):
                self.stopped = True

        fake_live = FakeLive()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={"merged": True}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value=None), \
             patch("src.dagdi.commands.service_management.resolve_scope", return_value=fake_scope), \
             patch("src.dagdi.commands.service_management.prepare_sudo_auth", return_value=True) as mock_prepare_sudo_auth, \
             patch("src.dagdi.commands.service_management.validate_sudo_auth") as mock_validate_sudo_auth, \
             patch("src.dagdi.commands.service_management.warm_up_connection") as mock_warm_up, \
             patch("src.dagdi.commands.service_management.execute_command", return_value=ExecutionResult(stdout="", return_code=0)), \
             patch("rich.live.Live", return_value=fake_live), \
             patch("src.dagdi.commands.service_management.time.sleep", side_effect=KeyboardInterrupt):
            result = runner.invoke(service_app, ["mas", "status", "--monitor"])

        assert result.exit_code == 0
        assert mock_prepare_sudo_auth.call_count == 2
        mock_prepare_sudo_auth.assert_any_call(sudo_server, "10.0.1.10")
        mock_prepare_sudo_auth.assert_any_call(sudo_server, "10.0.1.11")
        assert fake_live.started is True


class TestStatusCommandBuilder:
    """Tests for status command generation with runtime metrics."""

    def test_systemd_status_command_aggregates_cgroup_memory(self):
        """Systemd status should inspect the service cgroup, not only MainPID RSS."""
        service = Service(name="dagdi-app", type="systemd")

        command = _build_status_command_with_metrics(service, server_type="ubuntu")

        assert "ControlGroup" in command
        assert "memory.current" in command
        assert "cgroup.procs" in command
        assert "DAGDI_RAM_BYTES=" in command

    def test_systemd_status_command_wraps_full_script_for_sudo(self):
        """Sudo mode should execute the whole shell script as root."""
        service = Service(name="dagdi-app", type="systemd")

        command = _build_status_command_with_metrics(service, server_type="ubuntu", use_sudo=True)

        assert command.startswith("sudo sh -c ")

    def test_ms_status_targets_only_servers_with_requested_service(self, sample_config):
        """Should skip unrelated servers when resolving a specific service."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={"merged": True}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value=None), \
             patch("src.dagdi.commands.service_management.warm_up_connection"), \
             patch("src.dagdi.commands.service_management.prepare_sudo_auth"), \
             patch("src.dagdi.commands.service_management.validate_sudo_auth"), \
             patch("src.dagdi.commands.service_management.execute_command", return_value=ExecutionResult(stdout="active (running)", return_code=0)) as mock_execute:
            result = runner.invoke(service_app, ["ms", "nginx", "status", "-p", "myapp", "-e", "dev"])

        assert result.exit_code == 0
        assert "Service 'nginx' not found on server" not in result.stdout
        assert mock_execute.call_count == 2
        called_servers = [call.args[0].name for call in mock_execute.call_args_list]
        assert called_servers == ["web-1", "web-1"]

    def test_ms_status_executes_targets_in_parallel(self, sample_config):
        """Should fan out a single-service status request across matching targets."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()
        active_calls = 0
        max_active_calls = 0
        lock = threading.Lock()

        def fake_execute(*args, **kwargs):
            nonlocal active_calls, max_active_calls
            with lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.05)
            with lock:
                active_calls -= 1
            return ExecutionResult(stdout="active (running)", return_code=0)

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={"merged": True}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value=None), \
             patch("src.dagdi.commands.service_management.warm_up_connection"), \
             patch("src.dagdi.commands.service_management.prepare_sudo_auth"), \
             patch("src.dagdi.commands.service_management.validate_sudo_auth"), \
             patch("src.dagdi.commands.service_management.execute_command", side_effect=fake_execute):
            result = runner.invoke(service_app, ["ms", "nginx", "status", "-p", "myapp", "-e", "dev"])

        assert result.exit_code == 0
        assert max_active_calls > 1

    def test_mas_status_executes_servers_in_parallel(self, sample_config):
        """Should process different servers concurrently for all-services status."""
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()
        active_calls = 0
        max_active_calls = 0
        lock = threading.Lock()

        def fake_execute(*args, **kwargs):
            nonlocal active_calls, max_active_calls
            with lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.05)
            with lock:
                active_calls -= 1
            return ExecutionResult(stdout="active (running)", return_code=0)

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={"merged": True}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value=None), \
             patch("src.dagdi.commands.service_management.warm_up_connection"), \
             patch("src.dagdi.commands.service_management.prepare_sudo_auth"), \
             patch("src.dagdi.commands.service_management.validate_sudo_auth"), \
             patch("src.dagdi.commands.service_management.execute_command", side_effect=fake_execute):
            result = runner.invoke(service_app, ["mas", "status", "-p", "myapp", "-e", "dev"])

        assert result.exit_code == 0
        assert max_active_calls > 1


class TestServiceStatusDisplay:
    """Tests for status table rendering."""

    def test_display_status_results_includes_type_column(self, capsys):
        """Should show Type and metrics columns for single-service status output."""
        _display_status_results([
            {
                "server": "web-1",
                "ip": "10.0.1.10",
                "service": "nginx",
                "service_type": "systemd",
                "pid": "1234",
                "cpu": "1.2%",
                "ram": "64.0MB",
                "since": "Mon 2026-03-22 12:00:00 UTC",
                "status": "RUNNING",
                "success": True,
            }
        ])

        captured = capsys.readouterr()
        assert "Type" in captured.out
        assert "PID" in captured.out
        assert "CPU" in captured.out
        assert "RAM" in captured.out
        assert "Since" in captured.out
        assert "1234" in captured.out

    def test_display_consolidated_status_includes_type_column(self, capsys):
        """Should show Type and metrics columns for all-services status output."""
        _display_consolidated_status([
            {
                "server": "web-1",
                "ip": "10.0.1.10",
                "service": "api",
                "service_type": "docker",
                "pid": "-",
                "cpu": "2.1%",
                "ram": "128MiB",
                "since": "2026-03-22T12:00:00Z",
                "status": "RUNNING",
                "success": True,
            }
        ])

        captured = capsys.readouterr()
        assert "Type" in captured.out
        assert "PID" in captured.out
        assert "CPU" in captured.out
        assert "RAM" in captured.out
        assert "Since" in captured.out
        assert "docker" in captured.out
        assert "2.1%" in captured.out


class TestParseServiceMetrics:
    """Tests for _parse_service_metrics function."""

    def test_parse_systemd_metrics(self):
        """Should parse PID, CPU, and RAM for systemd status output."""
        result = ExecutionResult(
            stdout="DAGDI_PID=1234\nDAGDI_CPU=3.1%\nDAGDI_RAM=42.0MB\nDAGDI_SINCE=Mon 2026-03-22 12:00:00 UTC\n",
            return_code=0,
        )
        metrics = _parse_service_metrics(result, "systemd")
        assert metrics["pid"] == "1234"
        assert metrics["cpu"] == "3.1%"
        assert metrics["ram"] == "42.0MB"
        assert metrics["since"] == "Mon 2026-03-22 12:00:00 UTC"

    def test_parse_docker_metrics(self):
        """Should parse CPU and RAM for docker status output and keep PID as '-'."""
        result = ExecutionResult(
            stdout="DAGDI_CPU=0.8%\nDAGDI_RAM=19.3MiB\nDAGDI_SINCE=2026-03-22T12:00:00Z\n",
            return_code=0,
        )
        metrics = _parse_service_metrics(result, "docker")
        assert metrics["pid"] == "-"
        assert metrics["cpu"] == "0.8%"
        assert metrics["ram"] == "19.3MiB"
        assert metrics["since"] == "2026-03-22T12:00:00Z"


class TestBuildStatusCommandWithMetrics:
    """Tests for status command construction."""

    def test_build_systemd_command_centos_uses_legacy_show_parsing(self):
        service = Service(name="sshd", type="systemd")
        command = _build_status_command_with_metrics(service, server_type="centos7", use_sudo=True)

        assert "systemctl show -p MainPID sshd 2>/dev/null" in command
        assert "systemctl show -p MainPID --value" not in command
        assert "systemctl show -p LoadState --value" not in command
        assert "sed" in command
        assert command.startswith("sudo sh -c ")

    def test_build_docker_command_uses_state_marker(self):
        service = Service(name="api", type="docker", config={"container_name": "api"})
        command = _build_status_command_with_metrics(service, server_type="ubuntu", use_sudo=False)

        assert "DAGDI_DOCKER_STATE=$STATE" in command
        assert "DAGDI_STATUS=NOT_FOUND" in command

    def test_build_docker_command_with_sudo_wraps_entire_script(self):
        service = Service(name="api", type="docker", config={"container_name": "api"})
        command = _build_status_command_with_metrics(service, server_type="ubuntu", use_sudo=True)

        assert command.startswith("sudo sh -c ")
        assert "DAGDI_DOCKER_STATE=$STATE" in command
