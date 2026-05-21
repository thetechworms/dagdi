"""Unit tests for log streaming commands."""

import pytest
from unittest.mock import patch, MagicMock, Mock
from io import StringIO

from src.dagdi.commands.logs import logs, _build_log_command
from src.dagdi.models import (
    Configuration, Product, Environment, Server, Service, SSHConfig, Context
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
        ips=["10.0.1.10"],
        ssh_config=ssh_config,
        services=[service1, service2]
    )
    
    env_dev = Environment(name="dev", servers=[server1])
    product1 = Product(name="myapp", environments=[env_dev])
    
    return Configuration(products=[product1])


@pytest.fixture
def sample_context():
    """Create a sample context for testing."""
    return {"product": "myapp", "environment": "dev"}


class TestBuildLogCommand:
    """Tests for _build_log_command function."""
    
    def test_systemd_log_command(self):
        """Test building log command for systemd service."""
        service = Service(name="nginx", type="systemd")
        cmd = _build_log_command(service)
        assert cmd == "journalctl -u nginx -f"
    
    def test_systemd_log_command_with_sudo(self):
        """Test building log command for systemd service with sudo."""
        service = Service(name="nginx", type="systemd")
        cmd = _build_log_command(service, use_sudo=True)
        assert cmd == "sudo journalctl -u nginx -f"

    def test_systemd_uses_custom_log_command_when_configured(self):
        """Test systemd service uses custom log_command when provided."""
        service = Service(
            name="syslog",
            type="systemd",
            config={"log_command": "tail -f /var/log/syslog"},
        )
        cmd = _build_log_command(service)
        assert cmd == "tail -f /var/log/syslog"

    def test_systemd_log_command_with_sudo_uses_centralized_executor_handling(self):
        """Test log command leaves sudo normalization to the SSH executor."""
        service = Service(name="nginx", type="systemd")
        cmd = _build_log_command(service, use_sudo=True)
        assert cmd == "sudo journalctl -u nginx -f"
    
    def test_docker_log_command(self):
        """Test building log command for docker service."""
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        cmd = _build_log_command(service)
        assert cmd == "docker logs -f api-container"
    
    def test_docker_log_command_default_container_name(self):
        """Test building log command for docker service with default container name."""
        service = Service(name="api", type="docker")
        cmd = _build_log_command(service)
        assert cmd == "docker logs -f api"
    
    def test_docker_log_command_with_sudo(self):
        """Test building log command for docker service with sudo."""
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        cmd = _build_log_command(service, use_sudo=True)
        assert cmd == "sudo docker logs -f api-container"

    def test_docker_uses_custom_log_command_when_configured(self):
        """Test docker service uses custom log_command when provided."""
        service = Service(
            name="api",
            type="docker",
            config={"container_name": "api-container", "log_command": "tail -f /tmp/api.log"},
        )
        cmd = _build_log_command(service)
        assert cmd == "tail -f /tmp/api.log"
    
    def test_unknown_service_type(self):
        """Test building log command for unknown service type."""
        service = Service(name="unknown", type="unknown")
        with pytest.raises(ValueError, match="Unknown service type"):
            _build_log_command(service)


class TestLogsCommand:
    """Tests for logs command."""
    
    @patch('src.dagdi.commands.logs.execute_command_stream')
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_basic(self, mock_load, mock_merge, mock_validate, mock_get_context, mock_stream):
        """Test basic logs command."""
        # Setup
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
            services=[service]
        )
        env = Environment(name="dev", servers=[server])
        product = Product(name="myapp", environments=[env])
        config = Configuration(products=[product])
        
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_get_context.return_value = {"product": "myapp", "environment": "dev"}
        
        # Execute
        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app
        
        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])
        
        # Verify
        assert result.exit_code == 0
        mock_stream.assert_called_once()
    
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_service_not_found(self, mock_load, mock_merge, mock_validate, mock_get_context):
        """Test logs command when service not found."""
        # Setup
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
            services=[service]
        )
        env = Environment(name="dev", servers=[server])
        product = Product(name="myapp", environments=[env])
        config = Configuration(products=[product])
        
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_get_context.return_value = {"product": "myapp", "environment": "dev"}
        
        # Execute
        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app
        
        runner = CliRunner()
        result = runner.invoke(logs_app, ["postgres"])
        
        # Verify
        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "not found" in output.lower()
    
    @patch('src.dagdi.commands.logs.execute_command_stream')
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_with_server_filter(self, mock_load, mock_merge, mock_validate, mock_get_context, mock_stream):
        """Test logs command with server filter."""
        # Setup
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
        service = Service(name="nginx", type="systemd")
        server1 = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
            services=[service]
        )
        server2 = Server(
            name="web-2",
            type="ubuntu",
            ips=["10.0.1.11"],
            ssh_config=ssh_config,
            services=[service]
        )
        env = Environment(name="dev", servers=[server1, server2])
        product = Product(name="myapp", environments=[env])
        config = Configuration(products=[product])
        
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_get_context.return_value = {"product": "myapp", "environment": "dev"}
        
        # Execute
        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app
        
        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--server", "web-1"])
        
        # Verify
        assert result.exit_code == 0
        mock_stream.assert_called_once()
        # Verify it was called with web-1
        call_args = mock_stream.call_args
        assert call_args[0][0].name == "web-1"
    
    @patch('src.dagdi.commands.logs.execute_command_stream')
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_with_ip_filter(self, mock_load, mock_merge, mock_validate, mock_get_context, mock_stream):
        """Test logs command with IP filter."""
        # Setup - server with single IP to test IP filtering
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
        service = Service(name="nginx", type="systemd")
        server1 = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
            services=[service]
        )
        server2 = Server(
            name="web-2",
            type="ubuntu",
            ips=["10.0.1.11"],
            ssh_config=ssh_config,
            services=[service]
        )
        env = Environment(name="dev", servers=[server1, server2])
        product = Product(name="myapp", environments=[env])
        config = Configuration(products=[product])
        
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_get_context.return_value = {"product": "myapp", "environment": "dev"}
        
        # Execute
        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app
        
        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx", "--ip", "10.0.1.11"])
        
        # Verify
        assert result.exit_code == 0
        mock_stream.assert_called_once()
        # Verify it was called with correct IP
        call_args = mock_stream.call_args
        assert call_args[0][1] == "10.0.1.11"

    @patch('src.dagdi.commands.logs.execute_command_stream')
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_prompts_for_sudo_password_at_runtime(
        self, mock_load, mock_merge, mock_validate, mock_get_context, mock_stream
    ):
        """Test logs delegates sudo prompting to the SSH executor."""
        ssh_config = SSHConfig(
            username="ubuntu",
            key_path="~/.ssh/id_rsa",
            sudo=True,
            sudo_password=None,
        )
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
            services=[service]
        )
        env = Environment(name="dev", servers=[server])
        product = Product(name="myapp", environments=[env])
        config = Configuration(products=[product])

        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_get_context.return_value = {"product": "myapp", "environment": "dev"}

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])

        assert result.exit_code == 0
        call_args = mock_stream.call_args
        assert call_args[0][2] == "sudo journalctl -u nginx -f"

    @patch('src.dagdi.commands.logs.execute_command_stream')
    @patch('src.dagdi.commands.logs.get_context')
    @patch('src.dagdi.commands.logs.validate_configuration')
    @patch('src.dagdi.commands.logs.merge_configurations')
    @patch('src.dagdi.commands.logs.load_all_configurations')
    def test_logs_does_not_prompt_for_root_user(
        self, mock_load, mock_merge, mock_validate, mock_get_context, mock_stream
    ):
        """Test logs does not use sudo or prompt when SSH user is root."""
        ssh_config = SSHConfig(
            username="root",
            key_path="~/.ssh/id_rsa",
            sudo=True,
            sudo_password=None,
        )
        service = Service(name="nginx", type="systemd")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
            services=[service]
        )
        env = Environment(name="dev", servers=[server])
        product = Product(name="myapp", environments=[env])
        config = Configuration(products=[product])

        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = config
        mock_get_context.return_value = {"product": "myapp", "environment": "dev"}

        from typer.testing import CliRunner
        from src.dagdi.commands.logs import logs_app

        runner = CliRunner()
        result = runner.invoke(logs_app, ["nginx"])

        assert result.exit_code == 0
        call_args = mock_stream.call_args
        assert call_args[0][2] == "journalctl -u nginx -f"
