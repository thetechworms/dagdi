"""Unit tests for service-specific command generation."""

import pytest

from src.dagdi.ssh.command_builder import CommandBuilder
from src.dagdi.models import Service


class TestCommandBuilder:
    """Tests for CommandBuilder class."""
    
    def test_build_systemd_start_command(self):
        """Test building systemctl start command."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.build_command(service, "start")
        
        assert command == "systemctl start nginx"
    
    def test_build_systemd_stop_command(self):
        """Test building systemctl stop command."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.build_command(service, "stop")
        
        assert command == "systemctl stop nginx"
    
    def test_build_systemd_restart_command(self):
        """Test building systemctl restart command."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.build_command(service, "restart")
        
        assert command == "systemctl restart nginx"
    
    def test_build_systemd_status_command(self):
        """Test building systemctl status command."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.build_command(service, "status")
        
        assert command == "systemctl status nginx"
    
    def test_build_systemd_invalid_action(self):
        """Test that invalid action raises error."""
        service = Service(name="nginx", type="systemd")
        
        with pytest.raises(ValueError, match="Invalid action for systemd"):
            CommandBuilder.build_command(service, "invalid")
    
    def test_build_docker_start_command(self):
        """Test building docker start command."""
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        command = CommandBuilder.build_command(service, "start")
        
        assert command == "docker start api-container"
    
    def test_build_docker_stop_command(self):
        """Test building docker stop command."""
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        command = CommandBuilder.build_command(service, "stop")
        
        assert command == "docker stop api-container"
    
    def test_build_docker_restart_command(self):
        """Test building docker restart command."""
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        command = CommandBuilder.build_command(service, "restart")
        
        assert command == "docker restart api-container"
    
    def test_build_docker_status_command(self):
        """Test building docker status command."""
        service = Service(name="api", type="docker", config={"container_name": "api-container"})
        command = CommandBuilder.build_command(service, "status")
        
        assert "docker ps" in command
        assert "api-container" in command
    
    def test_build_docker_uses_service_name_as_default(self):
        """Test that docker uses service name if container_name not specified."""
        service = Service(name="api", type="docker")
        command = CommandBuilder.build_command(service, "start")
        
        assert command == "docker start api"
    
    def test_build_docker_invalid_action(self):
        """Test that invalid action raises error."""
        service = Service(name="api", type="docker")
        
        with pytest.raises(ValueError, match="Invalid action for docker"):
            CommandBuilder.build_command(service, "invalid")
    
    def test_build_command_with_sudo(self):
        """Test building command with sudo."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.build_command(service, "restart", use_sudo=True)
        
        assert command == "sudo systemctl restart nginx"
    
    def test_build_unknown_service_type(self):
        """Test that unknown service type raises error."""
        service = Service(name="app", type="unknown")
        
        with pytest.raises(ValueError, match="Unknown service type"):
            CommandBuilder.build_command(service, "start")
    
    def test_get_status_command(self):
        """Test get_status_command helper."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.get_status_command(service)
        
        assert command == "systemctl status nginx"
    
    def test_get_start_command(self):
        """Test get_start_command helper."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.get_start_command(service)
        
        assert command == "systemctl start nginx"
    
    def test_get_start_command_with_sudo(self):
        """Test get_start_command with sudo."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.get_start_command(service, use_sudo=True)
        
        assert command == "sudo systemctl start nginx"
    
    def test_get_stop_command(self):
        """Test get_stop_command helper."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.get_stop_command(service)
        
        assert command == "systemctl stop nginx"
    
    def test_get_restart_command(self):
        """Test get_restart_command helper."""
        service = Service(name="nginx", type="systemd")
        command = CommandBuilder.get_restart_command(service)
        
        assert command == "systemctl restart nginx"
