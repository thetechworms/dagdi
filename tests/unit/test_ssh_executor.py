"""Unit tests for SSH command execution."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from paramiko.ssh_exception import SSHException, AuthenticationException

from src.dagdi.ssh.executor import (
    execute_command,
    execute_command_with_sudo,
    ExecutionError,
    prepare_sudo_auth,
)
from src.dagdi.models import Server, SSHConfig, ExecutionResult


@pytest.fixture(autouse=True)
def clear_sudo_caches():
    """Keep sudo cache state isolated across tests."""
    from src.dagdi.ssh import executor as executor_module

    executor_module._SUDO_PASSWORD_CACHE.clear()
    executor_module._SUDO_NOPASSWD_CACHE.clear()
    yield
    executor_module._SUDO_PASSWORD_CACHE.clear()
    executor_module._SUDO_NOPASSWD_CACHE.clear()


@pytest.fixture
def ssh_config():
    """Create a sample SSH configuration."""
    return SSHConfig(
        username="ubuntu",
        key_path="~/.ssh/id_rsa",
        timeout=30,
    )


@pytest.fixture
def server(ssh_config):
    """Create a sample server."""
    return Server(
        name="web-1",
        type="ubuntu",
        ips=["10.0.1.10"],
        ssh_config=ssh_config,
    )


class TestExecuteCommand:
    """Tests for execute_command function."""
    
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_success(self, mock_get_pool, server):
        """Test successful command execution."""
        # Setup mock
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client
        
        # Mock command output
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"output"
        mock_stdout.channel.recv_exit_status.return_value = 0
        
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        # Execute
        result = execute_command(server, "10.0.1.10", "echo hello")
        
        # Verify
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.return_code == 0
        assert result.success
        mock_client.exec_command.assert_called_once_with("echo hello", timeout=30)
    
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_with_stderr(self, mock_get_pool, server):
        """Test command execution with stderr output."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client
        
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"output"
        mock_stdout.channel.recv_exit_status.return_value = 1
        
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"error message"
        
        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        result = execute_command(server, "10.0.1.10", "false")
        
        assert result.stdout == "output"
        assert result.stderr == "error message"
        assert result.return_code == 1
        assert result.failed
    
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_with_custom_timeout(self, mock_get_pool, server):
        """Test command execution with custom timeout."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client
        
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b""
        mock_stdout.channel.recv_exit_status.return_value = 0
        
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        execute_command(server, "10.0.1.10", "sleep 1", timeout=60)
        
        # Verify custom timeout was used
        mock_client.exec_command.assert_called_once_with("sleep 1", timeout=60)
    
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_ssh_exception(self, mock_get_pool, server):
        """Test command execution with SSH exception."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client
        mock_client.exec_command.side_effect = SSHException("Connection lost")
        
        result = execute_command(server, "10.0.1.10", "echo hello")
        
        assert result.error is not None
        assert "SSH error" in result.error
        assert result.failed
    
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_generic_exception(self, mock_get_pool, server):
        """Test command execution with generic exception."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client
        mock_client.exec_command.side_effect = RuntimeError("Unexpected error")
        
        result = execute_command(server, "10.0.1.10", "echo hello")
        
        assert result.error is not None
        assert "Execution error" in result.error
        assert result.failed
    
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_utf8_decoding(self, mock_get_pool, server):
        """Test command execution with UTF-8 output."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client
        
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = "Hello 世界".encode('utf-8')
        mock_stdout.channel.recv_exit_status.return_value = 0
        
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        result = execute_command(server, "10.0.1.10", "echo hello")
        
        assert "世界" in result.stdout

    @patch('src.dagdi.ssh.executor.getpass.getpass', return_value='secret')
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_prompts_and_wraps_sudo(self, mock_get_pool, mock_getpass, server):
        """Test central sudo handling prompts and rewrites command."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client

        probe_stdout = MagicMock()
        probe_stdout.read.return_value = b""
        probe_stdout.channel.recv_exit_status.return_value = 1
        probe_stderr = MagicMock()
        probe_stderr.read.return_value = b"sudo: a password is required"

        cmd_stdout = MagicMock()
        cmd_stdout.read.return_value = b"ok"
        cmd_stdout.channel.recv_exit_status.return_value = 0
        cmd_stderr = MagicMock()
        cmd_stderr.read.return_value = b""

        mock_client.exec_command.side_effect = [
            (None, probe_stdout, probe_stderr),
            (None, cmd_stdout, cmd_stderr),
        ]

        result = execute_command(server, "10.0.1.10", "sudo systemctl stop cups")

        assert result.success
        mock_getpass.assert_called_once()
        called_command = mock_client.exec_command.call_args_list[-1][0][0]
        assert called_command == "echo secret | sudo -S systemctl stop cups"

    @patch('src.dagdi.ssh.executor.getpass.getpass')
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_uses_nopasswd_without_prompt(self, mock_get_pool, mock_getpass, server):
        """Test sudo command uses -n and skips password prompt when NOPASSWD is available."""
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client

        probe_stdout = MagicMock()
        probe_stdout.read.return_value = b""
        probe_stdout.channel.recv_exit_status.return_value = 0
        probe_stderr = MagicMock()
        probe_stderr.read.return_value = b""

        cmd_stdout = MagicMock()
        cmd_stdout.read.return_value = b"ok"
        cmd_stdout.channel.recv_exit_status.return_value = 0
        cmd_stderr = MagicMock()
        cmd_stderr.read.return_value = b""

        mock_client.exec_command.side_effect = [
            (None, probe_stdout, probe_stderr),
            (None, cmd_stdout, cmd_stderr),
        ]

        result = execute_command(server, "10.0.1.10", "sudo systemctl status sshd")

        assert result.success
        mock_getpass.assert_not_called()
        called_command = mock_client.exec_command.call_args_list[-1][0][0]
        assert called_command == "sudo -n systemctl status sshd"

    @patch('src.dagdi.ssh.executor.getpass.getpass')
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_execute_command_strips_sudo_for_root_user(self, mock_get_pool, mock_getpass):
        """Test central sudo handling removes sudo when SSH user is root."""
        root_server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=SSHConfig(username="root", timeout=30),
        )

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"ok"
        mock_stdout.channel.recv_exit_status.return_value = 0

        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""

        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)

        result = execute_command(root_server, "10.0.1.10", "sudo systemctl stop cups")

        assert result.success
        mock_getpass.assert_not_called()
        called_command = mock_client.exec_command.call_args[0][0]
        assert called_command == "systemctl stop cups"


class TestExecuteCommandWithSudo:
    """Tests for execute_command_with_sudo function."""
    
    @patch('src.dagdi.ssh.executor.execute_command')
    def test_execute_with_sudo_no_password(self, mock_execute, server):
        """Test sudo execution without password."""
        mock_execute.return_value = ExecutionResult(stdout="", return_code=0)
        
        execute_command_with_sudo(server, "10.0.1.10", "systemctl restart nginx")
        
        # Verify sudo was prepended
        call_args = mock_execute.call_args
        assert call_args[0][2] == "sudo systemctl restart nginx"
    
    @patch('src.dagdi.ssh.executor.execute_command')
    def test_execute_with_sudo_with_password(self, mock_execute):
        """Test sudo execution delegates password handling to execute_command."""
        ssh_config = SSHConfig(
            username="ubuntu",
            sudo_password="secret",
            timeout=30,
        )
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
        )
        
        mock_execute.return_value = ExecutionResult(stdout="", return_code=0)
        
        execute_command_with_sudo(server, "10.0.1.10", "systemctl restart nginx")
        
        call_args = mock_execute.call_args
        assert call_args[0][2] == "sudo systemctl restart nginx"


class TestPrepareSudoAuth:
    """Tests for sudo auth preflight."""

    @patch('src.dagdi.ssh.executor.getpass.getpass', return_value='secret')
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_prepare_sudo_auth_prompts_once_and_uses_cache(self, mock_get_pool, mock_getpass, server):
        """Should resolve sudo once before live mode and reuse the cached password."""
        server.ssh_config.sudo = True

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client

        probe_stdout = MagicMock()
        probe_stdout.read.return_value = b""
        probe_stdout.channel.recv_exit_status.return_value = 1
        probe_stderr = MagicMock()
        probe_stderr.read.return_value = b"sudo: a password is required"

        mock_client.exec_command.return_value = (None, probe_stdout, probe_stderr)

        assert prepare_sudo_auth(server, "10.0.1.10") is True
        assert prepare_sudo_auth(server, "10.0.1.10") is True
        mock_getpass.assert_called_once()

    @patch('src.dagdi.ssh.executor.getpass.getpass')
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_prepare_sudo_auth_uses_nopasswd_without_prompt(self, mock_get_pool, mock_getpass, server):
        """Should succeed without prompting when passwordless sudo is available."""
        server.ssh_config.sudo = True

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client

        probe_stdout = MagicMock()
        probe_stdout.read.return_value = b""
        probe_stdout.channel.recv_exit_status.return_value = 0
        probe_stderr = MagicMock()
        probe_stderr.read.return_value = b""

        mock_client.exec_command.return_value = (None, probe_stdout, probe_stderr)

        assert prepare_sudo_auth(server, "10.0.1.10") is True
        mock_getpass.assert_not_called()

    @patch('src.dagdi.ssh.executor.getpass.getpass', return_value='secret')
    @patch('src.dagdi.ssh.executor.get_connection_pool')
    def test_prepare_sudo_auth_reuses_environment_prompt_cache_across_servers(
        self, mock_get_pool, mock_getpass
    ):
        """Shared servers.ssh prompt should ask once and be reused across servers."""
        shared_cache_key = "myapp:prod:ubuntu:shared-sudo-password"
        shared_label = "myapp/prod servers (ubuntu)"

        server1 = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=SSHConfig(
                username="ubuntu",
                sudo=True,
                sudo_password_prompt=True,
                sudo_password_prompt_cache_key=shared_cache_key,
                sudo_password_prompt_label=shared_label,
            ),
        )
        server2 = Server(
            name="web-2",
            type="ubuntu",
            ips=["10.0.1.11"],
            ssh_config=SSHConfig(
                username="ubuntu",
                sudo=True,
                sudo_password_prompt=True,
                sudo_password_prompt_cache_key=shared_cache_key,
                sudo_password_prompt_label=shared_label,
            ),
        )

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        mock_client = MagicMock()
        mock_pool.get.return_value = mock_client

        probe_stdout = MagicMock()
        probe_stdout.read.return_value = b""
        probe_stdout.channel.recv_exit_status.return_value = 1
        probe_stderr = MagicMock()
        probe_stderr.read.return_value = b"sudo: a password is required"

        mock_client.exec_command.return_value = (None, probe_stdout, probe_stderr)

        assert prepare_sudo_auth(server1, "10.0.1.10") is True
        assert prepare_sudo_auth(server2, "10.0.1.11") is True
        mock_getpass.assert_called_once_with(
            "Sudo password for myapp/prod servers (ubuntu): "
        )
