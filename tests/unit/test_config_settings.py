"""Unit tests for configuration settings commands."""

import pytest
from unittest.mock import patch
from typer.testing import CliRunner

from src.dagdi.commands.config import app
from src.dagdi.models import Configuration, GlobalSettings, Product, Environment, Server, Service, SSHConfig


class TestShowSettings:
    """Tests for show_settings command."""
    
    @patch('src.dagdi.commands.config.validate_configuration')
    @patch('src.dagdi.commands.config.merge_configurations')
    @patch('src.dagdi.commands.config.load_all_configurations')
    def test_show_settings_default(self, mock_load, mock_merge, mock_validate):
        """Test showing default settings."""
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
        
        # Execute
        runner = CliRunner()
        result = runner.invoke(app, ["show-settings"])
        
        # Verify
        assert result.exit_code == 0
        assert "Product: myapp" in result.stdout
        assert "SSH Timeout: 30 seconds" in result.stdout
        assert "SSH Port: 22" in result.stdout
        assert "On Partial Failure: prompt" in result.stdout
        assert "Live Status Table: False" in result.stdout
        assert "Minimal Status: False" in result.stdout
        assert "Log Buffer Size: 5000" in result.stdout
