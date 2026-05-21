"""Unit tests for SSH connection pool."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from paramiko.ssh_exception import AuthenticationException, SSHException

from src.dagdi.ssh.connection_pool import ConnectionPool, get_connection_pool
from src.dagdi.models import SSHConfig


@pytest.fixture
def ssh_config():
    """Create a sample SSH configuration."""
    return SSHConfig(
        username="ubuntu",
        key_path="~/.ssh/id_rsa",
        timeout=30,
    )


@pytest.fixture
def connection_pool():
    """Create a connection pool instance."""
    return ConnectionPool()


class TestConnectionPool:
    """Tests for ConnectionPool class."""
    
    def test_pool_initialization(self, connection_pool):
        """Test that connection pool initializes correctly."""
        assert connection_pool._connections == {}
        assert connection_pool._ssh_config is not None
    
    @patch('paramiko.SSHClient')
    def test_get_creates_new_connection(self, mock_ssh_client, connection_pool, ssh_config):
        """Test that get() creates a new connection when none exists."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client
        
        with patch.object(connection_pool, '_create_connection', return_value=mock_client):
            result = connection_pool.get("web-1", "10.0.1.10", ssh_config)
        
        assert result == mock_client
        assert ("web-1", "10.0.1.10", "ubuntu") in connection_pool._connections
    
    @patch('paramiko.SSHClient')
    def test_get_reuses_existing_connection(self, mock_ssh_client, connection_pool, ssh_config):
        """Test that get() reuses existing connections."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client
        
        # Mock exec_command to simulate a working connection
        mock_client.exec_command.return_value = (None, MagicMock(), MagicMock())
        
        with patch.object(connection_pool, '_create_connection', return_value=mock_client):
            # First call creates connection
            result1 = connection_pool.get("web-1", "10.0.1.10", ssh_config)
            
            # Second call should reuse it
            result2 = connection_pool.get("web-1", "10.0.1.10", ssh_config)
        
        assert result1 == result2
        assert result1 == mock_client
    
    def test_resolve_key_path_with_existing_key(self, connection_pool):
        """Test resolving SSH key path when key exists."""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.expanduser', return_value='/home/user/.ssh/id_rsa'):
                result = connection_pool._resolve_key_path('~/.ssh/id_rsa')
        
        assert result == '/home/user/.ssh/id_rsa'
    
    def test_resolve_key_path_with_nonexistent_key(self, connection_pool):
        """Test resolving SSH key path when key doesn't exist."""
        with patch('os.path.exists', return_value=False):
            result = connection_pool._resolve_key_path('~/.ssh/id_rsa')
        
        assert result is None
    
    def test_resolve_key_path_checks_defaults(self, connection_pool):
        """Test that default key locations are checked."""
        def exists_side_effect(path):
            return path == '/home/user/.ssh/id_ed25519'
        
        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('os.path.expanduser', side_effect=lambda x: x.replace('~', '/home/user')):
                result = connection_pool._resolve_key_path(None)
        
        assert result == '/home/user/.ssh/id_ed25519'
    
    @patch('paramiko.SSHClient')
    def test_create_connection_with_key(self, mock_ssh_client, connection_pool, ssh_config):
        """Test creating connection with SSH key."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client
        
        with patch.object(connection_pool, '_resolve_key_path', return_value='/home/user/.ssh/id_rsa'):
            result = connection_pool._create_connection("web-1", "10.0.1.10", ssh_config)
        
        assert result == mock_client
        mock_client.connect.assert_called_once()
        call_kwargs = mock_client.connect.call_args[1]
        assert call_kwargs['username'] == 'ubuntu'
        assert call_kwargs['key_filename'] == '/home/user/.ssh/id_rsa'
    
    @patch('paramiko.SSHClient')
    def test_create_connection_with_password(self, mock_ssh_client, connection_pool):
        """Test creating connection with password."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client
        
        ssh_config = SSHConfig(
            username="ubuntu",
            password="secret",
            timeout=30,
        )
        
        with patch.object(connection_pool, '_resolve_key_path', return_value=None):
            result = connection_pool._create_connection("web-1", "10.0.1.10", ssh_config)
        
        assert result == mock_client
        mock_client.connect.assert_called_once()
        call_kwargs = mock_client.connect.call_args[1]
        assert call_kwargs['password'] == 'secret'

    @patch('paramiko.SSHClient')
    def test_create_connection_prompts_password_on_auth_failure(self, mock_ssh_client, connection_pool):
        """Should prompt for SSH password and retry when default auth fails."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client

        ssh_config = SSHConfig(
            username="ubuntu",
            timeout=30,
        )

        mock_client.connect.side_effect = [
            AuthenticationException("auth failed"),
            None,
        ]

        with patch.object(connection_pool, '_resolve_key_path', return_value=None):
            with patch.object(connection_pool, '_prompt_for_password', return_value="secret"):
                result = connection_pool._create_connection("web-1", "10.0.1.10", ssh_config)

        assert result == mock_client
        assert mock_client.connect.call_count == 2
        second_call_kwargs = mock_client.connect.call_args_list[1][1]
        assert second_call_kwargs["password"] == "secret"

    @patch('paramiko.SSHClient')
    def test_create_connection_auth_failure_without_prompted_password(self, mock_ssh_client, connection_pool):
        """Should raise SSHException when auth fails and no password is provided."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client

        ssh_config = SSHConfig(
            username="ubuntu",
            timeout=30,
        )

        mock_client.connect.side_effect = AuthenticationException("auth failed")

        with patch.object(connection_pool, '_resolve_key_path', return_value=None):
            with patch.object(connection_pool, '_prompt_for_password', return_value=None):
                with pytest.raises(SSHException):
                    connection_pool._create_connection("web-1", "10.0.1.10", ssh_config)
    
    def test_close_connection(self, connection_pool, ssh_config):
        """Test closing a specific connection."""
        mock_client = MagicMock()
        pool_key = ("web-1", "10.0.1.10", "ubuntu")
        connection_pool._connections[pool_key] = mock_client
        
        connection_pool.close("web-1", "10.0.1.10", "ubuntu")
        
        assert pool_key not in connection_pool._connections
        mock_client.close.assert_called_once()
    
    def test_close_all_connections(self, connection_pool):
        """Test closing all connections."""
        mock_client1 = MagicMock()
        mock_client2 = MagicMock()
        
        connection_pool._connections[("web-1", "10.0.1.10", "ubuntu")] = mock_client1
        connection_pool._connections[("db-1", "10.0.2.10", "ubuntu")] = mock_client2
        
        connection_pool.close_all()
        
        assert len(connection_pool._connections) == 0
        mock_client1.close.assert_called_once()
        mock_client2.close.assert_called_once()


class TestGlobalConnectionPool:
    """Tests for global connection pool."""
    
    def test_get_connection_pool_returns_singleton(self):
        """Test that get_connection_pool returns the same instance."""
        pool1 = get_connection_pool()
        pool2 = get_connection_pool()
        
        assert pool1 is pool2
