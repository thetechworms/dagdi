"""Service-specific command generation."""

import logging
from typing import Optional

from dagdi.models import Service

logger = logging.getLogger(__name__)


class CommandBuilder:
    """Generates service-specific commands."""
    
    @staticmethod
    def build_command(
        service: Service,
        action: str,
        use_sudo: bool = False,
    ) -> str:
        """
        Build a command for a service action.
        
        Args:
            service: Service object
            action: Action to perform (start, stop, restart, status)
            use_sudo: Whether to prepend sudo
        
        Returns:
            Command string to execute
        
        Raises:
            ValueError: If service type is unknown or action is invalid
        """
        if service.type == "systemd":
            command = CommandBuilder._build_systemd_command(service, action)
        elif service.type == "docker":
            command = CommandBuilder._build_docker_command(service, action)
        else:
            raise ValueError(f"Unknown service type: {service.type}")
        
        if use_sudo:
            command = f"sudo {command}"
        
        return command
    
    @staticmethod
    def _build_systemd_command(service: Service, action: str) -> str:
        """Build systemctl command."""
        valid_actions = ["start", "stop", "restart", "status", "enable", "disable"]
        if action not in valid_actions:
            raise ValueError(f"Invalid action for systemd: {action}")
        
        return f"systemctl {action} {service.name}"
    
    @staticmethod
    def _build_docker_command(service: Service, action: str) -> str:
        """Build docker command."""
        valid_actions = ["start", "stop", "restart", "status"]
        if action not in valid_actions:
            raise ValueError(f"Invalid action for docker: {action}")
        
        # Get container name from config or use service name
        container_name = service.config.get("container_name", service.name)
        
        # Map actions to docker commands
        if action == "status":
            return f"docker ps --filter name={container_name} --format '{{{{.Status}}}}'"
        else:
            return f"docker {action} {container_name}"
    
    @staticmethod
    def get_status_command(service: Service) -> str:
        """Get the status command for a service."""
        return CommandBuilder.build_command(service, "status")
    
    @staticmethod
    def get_start_command(service: Service, use_sudo: bool = False) -> str:
        """Get the start command for a service."""
        return CommandBuilder.build_command(service, "start", use_sudo)
    
    @staticmethod
    def get_stop_command(service: Service, use_sudo: bool = False) -> str:
        """Get the stop command for a service."""
        return CommandBuilder.build_command(service, "stop", use_sudo)
    
    @staticmethod
    def get_restart_command(service: Service, use_sudo: bool = False) -> str:
        """Get the restart command for a service."""
        return CommandBuilder.build_command(service, "restart", use_sudo)
