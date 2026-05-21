"""SSH connection pooling and management."""

import logging
import os
import getpass
import sys
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple
import paramiko
from paramiko.ssh_exception import (
    SSHException,
    AuthenticationException,
    NoValidConnectionsError,
)

from dagdi.models import SSHConfig

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Manages SSH connections with pooling and reuse."""
    
    def __init__(self):
        """Initialize the connection pool."""
        self._connections: Dict[Tuple[str, str, str], paramiko.SSHClient] = {}
        self._lock = threading.RLock()
        self._ssh_config = paramiko.SSHConfig()
        self._load_ssh_config()
    
    def _load_ssh_config(self) -> None:
        """Load SSH config file if it exists."""
        ssh_config_path = Path.home() / ".ssh" / "config"
        if ssh_config_path.exists():
            try:
                self._ssh_config.parse(open(ssh_config_path))
                logger.debug(f"Loaded SSH config from {ssh_config_path}")
            except Exception as e:
                logger.warning(f"Failed to parse SSH config: {e}")
    
    def _resolve_key_path(self, key_path: Optional[str]) -> Optional[str]:
        """Resolve SSH key path, checking defaults if not specified."""
        if key_path:
            expanded = os.path.expanduser(key_path)
            if os.path.exists(expanded):
                return expanded
            logger.warning(f"SSH key not found: {expanded}")
            return None
        
        # Check default key locations
        default_keys = [
            "~/.ssh/id_rsa",
            "~/.ssh/id_ed25519",
            "~/.ssh/id_ecdsa",
            "~/.ssh/id_dsa",
        ]
        
        for key in default_keys:
            expanded = os.path.expanduser(key)
            if os.path.exists(expanded):
                logger.debug(f"Using default SSH key: {expanded}")
                return expanded
        
        return None
    
    def get(
        self,
        server_name: str,
        ip: str,
        ssh_config: SSHConfig,
    ) -> paramiko.SSHClient:
        """
        Get or create an SSH connection.
        
        Args:
            server_name: Name of the server
            ip: IP address to connect to
            ssh_config: SSH configuration
        
        Returns:
            Paramiko SSHClient instance
        
        Raises:
            SSHException: If connection fails
        """
        pool_key = (server_name, ip, ssh_config.username)

        with self._lock:
            # Return existing connection if available
            if pool_key in self._connections:
                client = self._connections[pool_key]
                try:
                    transport = client.get_transport()
                    if transport is None or not transport.is_active():
                        raise Exception("Transport not active")
                    logger.debug(f"Reusing connection to {server_name}@{ip}")
                    return client
                except Exception as e:
                    logger.debug(f"Connection to {server_name}@{ip} is dead: {e}")
                    self._connections.pop(pool_key, None)

            # Create new connection
            client = self._create_connection(server_name, ip, ssh_config)
            self._connections[pool_key] = client
            return client
    
    def _create_connection(
        self,
        server_name: str,
        ip: str,
        ssh_config: SSHConfig,
    ) -> paramiko.SSHClient:
        """
        Create a new SSH connection.
        
        Args:
            server_name: Name of the server
            ip: IP address to connect to
            ssh_config: SSH configuration
        
        Returns:
            Paramiko SSHClient instance
        
        Raises:
            SSHException: If connection fails
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Resolve SSH key path
            key_path = self._resolve_key_path(ssh_config.key_path)
            
            # Attempt connection
            if key_path:
                logger.debug(f"Connecting to {server_name}@{ip} with key {key_path}")
                client.connect(
                    ip,
                    port=ssh_config.port,
                    username=ssh_config.username,
                    key_filename=key_path,
                    timeout=ssh_config.timeout,
                    look_for_keys=True,
                    allow_agent=True,
                )
            elif ssh_config.password:
                logger.debug(f"Connecting to {server_name}@{ip} with password")
                client.connect(
                    ip,
                    port=ssh_config.port,
                    username=ssh_config.username,
                    password=ssh_config.password,
                    timeout=ssh_config.timeout,
                )
            else:
                logger.debug(f"Connecting to {server_name}@{ip} with default auth")
                try:
                    client.connect(
                        ip,
                        port=ssh_config.port,
                        username=ssh_config.username,
                        timeout=ssh_config.timeout,
                        look_for_keys=True,
                        allow_agent=True,
                    )
                except AuthenticationException:
                    password = self._prompt_for_password(server_name, ip, ssh_config.username)
                    if not password:
                        raise
                    logger.debug(f"Retrying {server_name}@{ip} with prompted password")
                    client.connect(
                        ip,
                        port=ssh_config.port,
                        username=ssh_config.username,
                        password=password,
                        timeout=ssh_config.timeout,
                    )
            
            logger.info(f"Connected to {server_name}@{ip}")
            return client
        
        except AuthenticationException as e:
            logger.error(f"Authentication failed for {server_name}@{ip}: {e}")
            raise SSHException(f"Authentication failed: {e}")
        except NoValidConnectionsError as e:
            logger.error(f"Connection refused to {server_name}@{ip}: {e}")
            raise SSHException(f"Connection refused: {e}")
        except Exception as e:
            logger.error(f"Failed to connect to {server_name}@{ip}: {e}")
            raise SSHException(f"Connection failed: {e}")

    def _prompt_for_password(self, server_name: str, ip: str, username: str) -> Optional[str]:
        """Prompt user for SSH password when interactive auth fallback is needed."""
        if not sys.stdin or not sys.stdin.isatty():
            logger.debug("Skipping password prompt: no interactive terminal")
            return None
        try:
            entered = getpass.getpass(f"SSH password for {username}@{server_name} ({ip}): ")
        except (EOFError, KeyboardInterrupt):
            return None
        return entered if entered else None
    
    def close(self, server_name: str, ip: str, username: str) -> None:
        """
        Close a specific connection.
        
        Args:
            server_name: Name of the server
            ip: IP address
            username: SSH username
        """
        pool_key = (server_name, ip, username)
        with self._lock:
            if pool_key in self._connections:
                try:
                    self._connections[pool_key].close()
                    logger.debug(f"Closed connection to {server_name}@{ip}")
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
                finally:
                    self._connections.pop(pool_key, None)
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for (server_name, ip, username), client in list(self._connections.items()):
                try:
                    client.close()
                    logger.debug(f"Closed connection to {server_name}@{ip}")
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
            self._connections.clear()
    
    def __del__(self):
        """Cleanup connections on object destruction."""
        self.close_all()


# Global connection pool instance
_pool: Optional[ConnectionPool] = None


def get_connection_pool() -> ConnectionPool:
    """Get or create the global connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool()
    return _pool
