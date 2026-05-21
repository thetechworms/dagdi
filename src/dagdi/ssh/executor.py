"""SSH command execution."""

import getpass
import logging
import queue
import shlex
import socket
import subprocess
import sys
import threading
from typing import Optional
from paramiko.ssh_exception import SSHException

from dagdi.models import Server, ExecutionResult, SSHConfig
from dagdi.ssh.connection_pool import get_connection_pool

logger = logging.getLogger(__name__)
_SUDO_PASSWORD_CACHE: dict[str, str] = {}
_SUDO_NOPASSWD_CACHE: dict[str, bool] = {}
_SUDO_PASSWORD_CACHE_LOCK = threading.RLock()
_SUDO_PASSWORD_PROMPTING: dict[str, threading.Event] = {}
_SUDO_PASSWORD_PROMPTING_LOCK = threading.RLock()


class ExecutionError(Exception):
    """Raised when SSH command execution fails."""
    pass


def _is_local_target(ip: str) -> bool:
    """Check whether command target should execute locally."""
    normalized = (ip or "").strip().lower()
    return normalized in {"localhost", "127.0.0.1", "::1"}


def _sudo_cache_key(server: Server, ip: str) -> str:
    """Build a stable cache key for sudo auth state."""
    ssh_username = (server.ssh_config.username or "").strip().lower()
    return f"{server.name}:{ip}:{ssh_username}"


def _sudo_password_cache_key(server: Server, ip: str) -> str:
    """Return the cache key for sudo passwords, honoring shared prompt scopes."""
    return server.ssh_config.sudo_password_prompt_cache_key or _sudo_cache_key(server, ip)


def _sudo_password_prompt_label(server: Server) -> str:
    """Return the human-readable target label for sudo prompts."""
    return (
        server.ssh_config.sudo_password_prompt_label
        or f"{server.ssh_config.username}@{server.name}"
    )


def _resolve_sudo_password(server: Server, ip: str, prompt_if_needed: bool = True) -> Optional[str]:
    """Resolve sudo password from config, cache, or an interactive prompt (thread-safe).
    
    This function ensures that when multiple threads need a sudo password with the same
    cache key, only one thread calls getpass.getpass(), and all threads receive the same
    password. This prevents multiple prompts and threading errors.
    
    Args:
        server: Server object with SSH configuration
        ip: IP address to connect to
        prompt_if_needed: Whether to prompt if password is not cached
    
    Returns:
        The sudo password, or None if not available and not prompting
    """
    # 1. Check if password is already configured in SSH config
    sudo_password = server.ssh_config.sudo_password
    if sudo_password:
        return sudo_password

    cache_key = _sudo_password_cache_key(server, ip)
    
    # 2. Check cache first (quick path without lock)
    sudo_password = _SUDO_PASSWORD_CACHE.get(cache_key)
    if sudo_password is not None or not prompt_if_needed:
        return sudo_password
    
    # 3. Check if another thread is already prompting for this key
    is_prompting_thread = False
    prompting_event = None
    
    with _SUDO_PASSWORD_PROMPTING_LOCK:
        if cache_key in _SUDO_PASSWORD_PROMPTING:
            # Another thread is prompting, we'll wait for it
            prompting_event = _SUDO_PASSWORD_PROMPTING[cache_key]
        else:
            # This thread will do the prompting
            prompting_event = threading.Event()
            _SUDO_PASSWORD_PROMPTING[cache_key] = prompting_event
            is_prompting_thread = True
    
    if not is_prompting_thread:
        # Wait for the other thread to finish prompting (outside any lock)
        prompting_event.wait()
        # Now the password should be in the cache
        return _SUDO_PASSWORD_CACHE.get(cache_key)
    
    # 4. This thread is responsible for prompting
    try:
        label = _sudo_password_prompt_label(server)
        sudo_password = getpass.getpass(f"Sudo password for {label}: ")
        
        # 5. Store in cache with lock
        with _SUDO_PASSWORD_CACHE_LOCK:
            _SUDO_PASSWORD_CACHE[cache_key] = sudo_password
        
        return sudo_password
    finally:
        # 6. Signal other threads that prompting is complete
        with _SUDO_PASSWORD_PROMPTING_LOCK:
            prompting_event.set()
            del _SUDO_PASSWORD_PROMPTING[cache_key]


def warm_up_connection(server: Server, ip: str) -> None:
    """Pre-establish an SSH connection so interactive auth happens before live displays."""
    if _is_local_target(ip):
        return
    try:
        pool = get_connection_pool()
        pool.get(server.name, ip, server.ssh_config)
    except Exception:
        pass


def prepare_sudo_auth(server: Server, ip: str, prompt_if_needed: bool = True) -> bool:
    """
    Prepare sudo authentication for a target before executing live-refresh commands.

    Returns True when sudo is ready to use without an interactive prompt during
    command execution, either because the SSH user is root, NOPASSWD sudo works,
    or a password is already available/resolved.
    """
    if not server.ssh_config.sudo:
        return True

    ssh_username = (server.ssh_config.username or "").strip().lower()
    if ssh_username == "root":
        return True

    sudo_nopasswd = server.ssh_config.sudo_nopasswd
    if sudo_nopasswd is None:
        sudo_nopasswd = _can_run_sudo_without_password(server, ip)
    if sudo_nopasswd:
        return True

    return bool(_resolve_sudo_password(server, ip, prompt_if_needed=prompt_if_needed))


def _normalize_sudo_command(server: Server, ip: str, command: str) -> str:
    """
    Normalize sudo usage for non-interactive SSH execution.

    - If command starts with plain `sudo ` and SSH user is root: remove sudo.
    - If command starts with plain `sudo ` and passwordless sudo is available:
      convert to `sudo -n ...` (non-interactive).
    - If command starts with plain `sudo ` and password is available/prompted:
      convert to `echo <password> | sudo -S ...`.
    - If command starts with plain `sudo ` and no password entered:
      use `sudo -n ...` (non-interactive fail-fast).
    """
    stripped = command.strip()
    if not stripped.startswith("sudo ") or stripped.startswith("sudo -"):
        return command

    command_without_sudo = stripped[len("sudo "):]
    ssh_username = (server.ssh_config.username or "").strip()
    ssh_username_lower = ssh_username.lower()

    # Root sessions do not need sudo.
    if ssh_username_lower == "root":
        return command_without_sudo

    sudo_nopasswd = server.ssh_config.sudo_nopasswd
    if sudo_nopasswd is None:
        sudo_nopasswd = _can_run_sudo_without_password(server, ip)
    if sudo_nopasswd:
        return f"sudo -n {command_without_sudo}"

    sudo_password = _resolve_sudo_password(server, ip)

    if sudo_password:
        escaped_password = shlex.quote(sudo_password)
        return f"echo {escaped_password} | sudo -S {command_without_sudo}"

    return f"sudo -n {command_without_sudo}"


def _can_run_sudo_without_password(server: Server, ip: str) -> bool:
    """Check whether sudo works non-interactively for this server/user target."""
    cache_key = _sudo_cache_key(server, ip)
    cached = _SUDO_NOPASSWD_CACHE.get(cache_key)
    if cached is not None:
        return cached

    probe_command = "sudo -n true"

    try:
        if _is_local_target(ip):
            probe = subprocess.run(
                probe_command,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=server.ssh_config.timeout,
            )
            is_nopasswd = probe.returncode == 0
        else:
            pool = get_connection_pool()
            client = pool.get(server.name, ip, server.ssh_config)
            _, stdout, stderr = client.exec_command(
                probe_command,
                timeout=server.ssh_config.timeout,
            )
            is_nopasswd = stdout.channel.recv_exit_status() == 0
            stdout.read()
            stderr.read()
            stdout.channel.close()
    except Exception:
        is_nopasswd = False

    _SUDO_NOPASSWD_CACHE[cache_key] = is_nopasswd
    return is_nopasswd


def execute_command(
    server: Server,
    ip: str,
    command: str,
    timeout: Optional[int] = None,
) -> ExecutionResult:
    """
    Execute a command on a remote server via SSH.
    
    Args:
        server: Server object with SSH configuration
        ip: IP address to connect to
        command: Command to execute
        timeout: Command timeout in seconds (overrides server config)
    
    Returns:
        ExecutionResult with stdout, stderr, and return_code
    """
    try:
        if _is_local_target(ip):
            return _execute_local_command(command, timeout)

        pool = get_connection_pool()

        # Use provided timeout or server's configured timeout
        effective_timeout = timeout or server.ssh_config.timeout

        command = _normalize_sudo_command(server, ip, command)

        # Get or create connection
        client = pool.get(server.name, ip, server.ssh_config)
        
        # Execute command with timeout
        logger.debug(f"Executing on {server.name}@{ip}: {command}")
        stdin, stdout, stderr = client.exec_command(command, timeout=effective_timeout)
        
        # Read output
        stdout_data = stdout.read().decode('utf-8', errors='replace')
        stderr_data = stderr.read().decode('utf-8', errors='replace')
        return_code = stdout.channel.recv_exit_status()
        
        logger.debug(
            f"Command completed on {server.name}@{ip} with return code {return_code}"
        )
        
        return ExecutionResult(
            stdout=stdout_data,
            stderr=stderr_data,
            return_code=return_code,
        )
    
    except SSHException as e:
        error_msg = f"SSH error on {server.name}@{ip}: {str(e)}"
        logger.error(error_msg)
        return ExecutionResult(error=error_msg)
    
    except Exception as e:
        error_msg = f"Execution error on {server.name}@{ip}: {str(e)}"
        logger.error(error_msg)
        return ExecutionResult(error=error_msg)


def execute_command_with_sudo(
    server: Server,
    ip: str,
    command: str,
    timeout: Optional[int] = None,
) -> ExecutionResult:
    """
    Execute a command with sudo privileges.
    
    Args:
        server: Server object with SSH configuration
        ip: IP address to connect to
        command: Command to execute (without sudo prefix)
        timeout: Command timeout in seconds
    
    Returns:
        ExecutionResult with stdout, stderr, and return_code
    """
    return execute_command(server, ip, f"sudo {command}", timeout)


def execute_command_stream(
    server: Server,
    ip: str,
    command: str,
    timeout: Optional[int] = None,
) -> None:
    """
    Execute a command and stream output in real-time.
    
    Args:
        server: Server object with SSH configuration
        ip: IP address to connect to
        command: Command to execute
        timeout: Command timeout in seconds (overrides server config)
    
    Raises:
        ExecutionError: If SSH connection fails
    """
    try:
        if _is_local_target(ip):
            _execute_local_stream(command, timeout)
            return

        pool = get_connection_pool()

        command = _normalize_sudo_command(server, ip, command)

        # Get or create connection
        client = pool.get(server.name, ip, server.ssh_config)

        # Execute command without channel timeout — streaming commands are
        # long-lived, so a socket-level timeout would kill the stream.
        logger.debug(f"Streaming from {server.name}@{ip}: {command}")
        stdin, stdout, stderr = client.exec_command(command)

        # Poll with short timeouts so Ctrl+C can interrupt on Windows.
        # Without this, channel.recv() blocks at the C/socket level and
        # Python never gets a chance to raise KeyboardInterrupt.
        channel = stdout.channel
        channel.settimeout(0.5)
        try:
            while True:
                try:
                    data = channel.recv(4096)
                    if not data:
                        break
                    sys.stdout.write(data.decode('utf-8', errors='replace'))
                    sys.stdout.flush()
                except socket.timeout:
                    if channel.exit_status_ready() and not channel.recv_ready():
                        break
        except KeyboardInterrupt:
            channel.close()
            raise

        # Check for errors
        return_code = stdout.channel.recv_exit_status()
        if return_code != 0:
            stderr_data = stderr.read().decode('utf-8', errors='replace')
            if stderr_data:
                logger.warning(f"Command stderr: {stderr_data}")

        logger.debug(
            f"Stream completed on {server.name}@{ip} with return code {return_code}"
        )
    
    except SSHException as e:
        error_msg = f"SSH error on {server.name}@{ip}: {str(e)}"
        logger.error(error_msg)
        raise ExecutionError(error_msg)
    
    except Exception as e:
        error_msg = f"Streaming error on {server.name}@{ip}: {str(e)}"
        logger.error(error_msg)
        raise ExecutionError(error_msg)


def _execute_local_command(command: str, timeout: Optional[int] = None) -> ExecutionResult:
    """Execute a shell command locally and return ExecutionResult."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return ExecutionResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            return_code=proc.returncode,
        )
    except Exception as e:
        return ExecutionResult(error=f"Local execution error: {str(e)}")


def _execute_local_stream(command: str, timeout: Optional[int] = None) -> None:
    """Execute a local command and stream output in real-time."""
    popen_kwargs = {
        "shell": True,
        "executable": "/bin/bash",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }

    process = subprocess.Popen(command, **popen_kwargs)

    # Read in a daemon thread so the main thread can catch Ctrl+C on Windows.
    # Pipe reads block at the OS level and swallow KeyboardInterrupt.
    line_queue: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line_queue.put(line)
        except Exception:
            pass
        finally:
            line_queue.put(None)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    try:
        while True:
            try:
                line = line_queue.get(timeout=0.5)
                if line is None:
                    break
                sys.stdout.write(line)
                sys.stdout.flush()
            except queue.Empty:
                if process.poll() is not None:
                    while not line_queue.empty():
                        line = line_queue.get_nowait()
                        if line is None:
                            break
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    break

        process.wait(timeout=timeout)
        if process.returncode not in (0, None):
            raise ExecutionError(f"Local stream command failed with code {process.returncode}")
    except KeyboardInterrupt:
        process.terminate()
        raise
    except Exception as e:
        process.terminate()
        raise ExecutionError(f"Local streaming error: {str(e)}")
