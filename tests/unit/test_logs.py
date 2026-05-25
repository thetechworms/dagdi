"""Unit tests for log streaming commands."""

import queue
import threading
import pytest
from unittest.mock import patch, MagicMock

from src.dagdi.commands.logs import (
    logs,
    _build_log_command,
    _resolve_log_targets,
    _LogTarget,
    _LogLine,
    _LABEL_COLORS,
)
from src.dagdi.models import (
    Configuration, GlobalSettings, Product, Environment, Server, Service, SSHConfig,
)


@pytest.fixture
def ssh_config():
    return SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")


@pytest.fixture
def ssh_config_sudo():
    return SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa", sudo=True)


@pytest.fixture
def ssh_config_root():
    return SSHConfig(username="root", key_path="~/.ssh/id_rsa", sudo=True)


@pytest.fixture
def service_nginx():
    return Service(name="nginx", type="systemd")


@pytest.fixture
def service_api():
    return Service(name="api", type="docker", config={"container_name": "api-container"})


@pytest.fixture
def service_friendly():
    return Service(name="pg-main", type="systemd", friendly_name="PostgreSQL")


@pytest.fixture
def server_web1(ssh_config, service_nginx, service_api):
    return Server(
        name="web-1", type="ubuntu", ips=["10.0.1.10"],
        ssh_config=ssh_config, services=[service_nginx, service_api],
    )


@pytest.fixture
def server_web2(ssh_config, service_nginx):
    return Server(
        name="web-2", type="ubuntu", ips=["10.0.1.11"],
        ssh_config=ssh_config, services=[service_nginx],
    )


@pytest.fixture
def server_db(ssh_config, service_friendly):
    return Server(
        name="db-1", type="ubuntu", ips=["10.0.2.10"],
        ssh_config=ssh_config, services=[service_friendly],
    )


@pytest.fixture
def sample_config(server_web1):
    env = Environment(name="dev", servers=[server_web1])
    product = Product(name="myapp", environments=[env])
    return Configuration(products=[product])


@pytest.fixture
def multi_server_config(server_web1, server_web2, server_db):
    env = Environment(name="dev", servers=[server_web1, server_web2, server_db])
    product = Product(name="myapp", environments=[env])
    return Configuration(products=[product])


@pytest.fixture
def sample_context():
    return {"product": "myapp", "environment": "dev"}


class TestBuildLogCommand:
    """Tests for _build_log_command function."""

    def test_systemd_log_command(self):
        service = Service(name="nginx", type="systemd")
        cmd = _build_log_command(service)
        assert cmd == "journalctl -u nginx -f"

    def test_systemd_log_command_with_sudo(self):
        service = Service(name="nginx", type="systemd")
        cmd = _build_log_command(service, use_sudo=True)
        assert cmd == "sudo journalctl -u nginx -f"

    def test_systemd_uses_custom_log_command_when_configured(self):
        service = Service(
            name="syslog", type="systemd",
            config={"log_command": "tail -f /var/log/syslog"},
        )
        cmd = _build_log_command(service)
        assert cmd == "tail -f /var/log/syslog"

    def test_systemd_log_command_with_sudo_uses_centralized_executor_handling(self):
        service = Service(name="nginx", type="systemd")
        cmd = _build_log_command(service, use_sudo=True)
        assert cmd == "sudo journalctl -u nginx -f"

    def test_docker_log_command(self):
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        cmd = _build_log_command(service)
        assert cmd == "docker logs -f api-container"

    def test_docker_log_command_default_container_name(self):
        service = Service(name="api", type="docker")
        cmd = _build_log_command(service)
        assert cmd == "docker logs -f api"

    def test_docker_log_command_with_sudo(self):
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        cmd = _build_log_command(service, use_sudo=True)
        assert cmd == "sudo docker logs -f api-container"

    def test_docker_uses_custom_log_command_when_configured(self):
        service = Service(
            name="api", type="docker",
            config={"container_name": "api-container", "log_command": "tail -f /tmp/api.log"},
        )
        cmd = _build_log_command(service)
        assert cmd == "tail -f /tmp/api.log"

    def test_unknown_service_type(self):
        service = Service(name="unknown", type="unknown")
        with pytest.raises(ValueError, match="Unknown service type"):
            _build_log_command(service)


class TestResolveLogTargets:
    """Tests for _resolve_log_targets function."""

    def test_single_service_single_server(self, server_web1):
        targets = _resolve_log_targets([server_web1], ["nginx"])
        assert len(targets) == 1
        assert targets[0].service.name == "nginx"
        assert targets[0].server.name == "web-1"
        assert targets[0].ip == "10.0.1.10"
        assert targets[0].label == "web-1/nginx"

    def test_single_service_multiple_servers(self, server_web1, server_web2):
        targets = _resolve_log_targets([server_web1, server_web2], ["nginx"])
        assert len(targets) == 2
        assert targets[0].server.name == "web-1"
        assert targets[1].server.name == "web-2"

    def test_multiple_services_single_server(self, server_web1):
        targets = _resolve_log_targets([server_web1], ["nginx", "api"])
        assert len(targets) == 2
        assert targets[0].service.name == "nginx"
        assert targets[1].service.name == "api"

    def test_multiple_services_multiple_servers(self, server_web1, server_web2, server_db):
        targets = _resolve_log_targets(
            [server_web1, server_web2, server_db],
            ["nginx", "pg-main"],
        )
        assert len(targets) == 3
        names = [(t.server.name, t.service.name) for t in targets]
        assert ("web-1", "nginx") in names
        assert ("web-2", "nginx") in names
        assert ("db-1", "pg-main") in names

    def test_friendly_name_matching(self, server_db):
        targets = _resolve_log_targets([server_db], ["PostgreSQL"])
        assert len(targets) == 1
        assert targets[0].service.name == "pg-main"
        assert targets[0].label == "db-1/PostgreSQL"

    def test_friendly_name_case_insensitive(self, server_db):
        targets = _resolve_log_targets([server_db], ["postgresql"])
        assert len(targets) == 1
        assert targets[0].service.name == "pg-main"

    def test_service_not_found(self, server_web1):
        targets = _resolve_log_targets([server_web1], ["nonexistent"])
        assert len(targets) == 0

    def test_colors_cycle_through_palette(self, server_web1, server_web2):
        targets = _resolve_log_targets([server_web1, server_web2], ["nginx"])
        assert targets[0].color == _LABEL_COLORS[0]
        assert targets[1].color == _LABEL_COLORS[1]

    def test_sudo_applied_when_configured(self):
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa", sudo=True)
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10"],
            ssh_config=ssh_config, services=[service],
        )
        targets = _resolve_log_targets([server], ["nginx"])
        assert targets[0].command == "sudo journalctl -u nginx -f"

    def test_no_sudo_for_root_user(self):
        ssh_config = SSHConfig(username="root", key_path="~/.ssh/id_rsa", sudo=True)
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10"],
            ssh_config=ssh_config, services=[service],
        )
        targets = _resolve_log_targets([server], ["nginx"])
        assert targets[0].command == "journalctl -u nginx -f"

    def test_docker_command_built_correctly(self, server_web1):
        targets = _resolve_log_targets([server_web1], ["api"])
        assert len(targets) == 1
        assert targets[0].command == "docker logs -f api-container"

    def test_server_with_no_ips_skipped(self):
        ssh_config = SSHConfig(username="ubuntu")
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=[],
            ssh_config=ssh_config, services=[service],
        )
        targets = _resolve_log_targets([server], ["nginx"])
        assert len(targets) == 0

    def test_uses_first_ip_when_multiple(self):
        ssh_config = SSHConfig(username="ubuntu")
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10", "10.0.1.11"],
            ssh_config=ssh_config, services=[service],
        )
        targets = _resolve_log_targets([server], ["nginx"])
        assert targets[0].ip == "10.0.1.10"


class TestLogsCommand:
    """Tests for logs command."""

    def _setup_mocks(self, mock_load, mock_merge, mock_validate, mock_ctx, config, context):
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_ctx.return_value = context

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_single_service(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        sample_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, sample_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])

        assert result.exit_code == 0
        mock_start.assert_called_once()
        targets = mock_start.call_args[0][0]
        assert len(targets) == 1
        assert targets[0].service.name == "nginx"

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_multiple_services(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        sample_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, sample_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "api"])

        assert result.exit_code == 0
        mock_start.assert_called_once()
        targets = mock_start.call_args[0][0]
        assert len(targets) == 2
        service_names = [t.service.name for t in targets]
        assert "nginx" in service_names
        assert "api" in service_names

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_with_server_filter(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        multi_server_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, multi_server_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--server", "web-1"])

        assert result.exit_code == 0
        mock_start.assert_called_once()
        targets = mock_start.call_args[0][0]
        assert len(targets) == 1
        assert targets[0].server.name == "web-1"

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_with_ip_filter(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        multi_server_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, multi_server_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--ip", "10.0.1.11"])

        assert result.exit_code == 0
        mock_start.assert_called_once()
        targets = mock_start.call_args[0][0]
        assert len(targets) == 1
        assert targets[0].ip == "10.0.1.11"

    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_service_not_found(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        sample_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, sample_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["postgres"])

        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "no matching services found" in output.lower()

    @patch('src.dagdi.commands.logs._display_split')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_split_layout(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        sample_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, sample_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--layout", "split"])

        assert result.exit_code == 0
        mock_display.assert_called_once()

    @patch('src.dagdi.commands.logs._display_split')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_split_passes_buffer_size_from_config(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        sample_context,
    ):
        settings = GlobalSettings(log_buffer_size=8000)
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10"],
            ssh_config=ssh_config, services=[service],
        )
        config = Configuration(
            products=[Product(
                name="myapp",
                environments=[Environment(name="dev", servers=[server])],
                global_settings=settings,
            )],
        )
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--layout", "split"])

        assert result.exit_code == 0
        mock_display.assert_called_once()
        call_kwargs = mock_display.call_args
        assert call_kwargs[1]["buffer_size"] == 8000

    def test_logs_invalid_layout(self, sample_config, sample_context):
        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--layout", "grid"])

        assert result.exit_code != 0

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.validate_sudo_auth')
    @patch('dagdi.ssh.executor.prepare_sudo_auth')
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_sudo_applied_for_non_root(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_prepare, mock_validate_sudo,
        mock_start, mock_display,
        sample_context,
    ):
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa", sudo=True)
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10"],
            ssh_config=ssh_config, services=[service],
        )
        config = Configuration(
            products=[Product(name="myapp", environments=[Environment(name="dev", servers=[server])])]
        )
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])

        assert result.exit_code == 0
        targets = mock_start.call_args[0][0]
        assert targets[0].command == "sudo journalctl -u nginx -f"

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.validate_sudo_auth')
    @patch('dagdi.ssh.executor.prepare_sudo_auth')
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_no_sudo_for_root(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_prepare, mock_validate_sudo,
        mock_start, mock_display,
        sample_context,
    ):
        ssh_config = SSHConfig(username="root", key_path="~/.ssh/id_rsa", sudo=True)
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10"],
            ssh_config=ssh_config, services=[service],
        )
        config = Configuration(
            products=[Product(name="myapp", environments=[Environment(name="dev", servers=[server])])]
        )
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])

        assert result.exit_code == 0
        targets = mock_start.call_args[0][0]
        assert targets[0].command == "journalctl -u nginx -f"

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_multi_service_across_servers(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        multi_server_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, multi_server_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "pg-main"])

        assert result.exit_code == 0
        targets = mock_start.call_args[0][0]
        assert len(targets) == 3
        pairs = [(t.server.name, t.service.name) for t in targets]
        assert ("web-1", "nginx") in pairs
        assert ("web-2", "nginx") in pairs
        assert ("db-1", "pg-main") in pairs

    @patch('src.dagdi.commands.logs._display_interleaved')
    @patch('src.dagdi.commands.logs._start_stream_threads', return_value=[])
    @patch('dagdi.ssh.executor.warm_up_connection')
    @patch('dagdi.ssh.executor._is_local_target', return_value=False)
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_warmup_called_per_target(
        self, mock_load, mock_merge, mock_validate, mock_ctx,
        mock_local, mock_warmup, mock_start, mock_display,
        multi_server_config, sample_context,
    ):
        self._setup_mocks(mock_load, mock_merge, mock_validate, mock_ctx, multi_server_config, sample_context)

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])

        assert result.exit_code == 0
        assert mock_warmup.call_count == 2


class TestDisplayInterleaved:
    """Tests for _display_interleaved output formatting."""

    def test_lines_printed_with_prefix(self):
        from src.dagdi.commands.logs import _display_interleaved

        ssh_config = SSHConfig(username="ubuntu")
        service = Service(name="nginx", type="systemd")
        server = Server(name="web-1", type="ubuntu", ips=["10.0.1.10"], ssh_config=ssh_config, services=[service])

        target = _LogTarget(
            server=server, ip="10.0.1.10", service=service,
            command="journalctl -u nginx -f", label="web-1/nginx", color="cyan",
        )

        line_queue: queue.Queue[_LogLine] = queue.Queue()
        stop_event = threading.Event()

        line_queue.put(_LogLine(target=target, text="test log line"))
        line_queue.put(_LogLine(target=target, text="", is_eof=True))

        _display_interleaved([target], line_queue, stop_event)

    def test_error_lines_marked(self):
        from src.dagdi.commands.logs import _display_interleaved

        ssh_config = SSHConfig(username="ubuntu")
        service = Service(name="nginx", type="systemd")
        server = Server(name="web-1", type="ubuntu", ips=["10.0.1.10"], ssh_config=ssh_config, services=[service])

        target = _LogTarget(
            server=server, ip="10.0.1.10", service=service,
            command="journalctl -u nginx -f", label="web-1/nginx", color="cyan",
        )

        line_queue: queue.Queue[_LogLine] = queue.Queue()
        stop_event = threading.Event()

        line_queue.put(_LogLine(target=target, text="connection lost", is_error=True))
        line_queue.put(_LogLine(target=target, text="", is_eof=True))

        _display_interleaved([target], line_queue, stop_event)
