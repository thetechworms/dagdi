"""Integration tests for Dagdi CLI - Phase 13."""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from src.dagdi.cli import app
from src.dagdi.models import (
    Configuration, Product, Environment, Server, Service, SSHConfig, GlobalSettings
)


@pytest.fixture
def sample_config():
    """Create a comprehensive sample configuration for integration testing."""
    ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa", timeout=30)
    
    # Services
    nginx = Service(name="nginx", type="systemd")
    api = Service(name="api", type="docker", config={"container_name": "api-container"})
    postgres = Service(name="postgres", type="systemd")
    
    # Servers
    web1 = Server(
        name="web-1",
        type="ubuntu",
        ips=["10.0.1.10"],
        ssh_config=ssh_config,
        services=[nginx, api]
    )
    web2 = Server(
        name="web-2",
        type="ubuntu",
        ips=["10.0.1.11"],
        ssh_config=ssh_config,
        services=[nginx, api]
    )
    db1 = Server(
        name="db-1",
        type="ubuntu",
        ips=["10.0.2.10"],
        ssh_config=ssh_config,
        services=[postgres]
    )
    
    # Environments
    dev_env = Environment(name="dev", servers=[web1, db1])
    prod_env = Environment(name="prod", servers=[web1, web2, db1])
    
    # Products
    product = Product(name="myapp", environments=[dev_env, prod_env])
    
    # Configuration
    settings = GlobalSettings(ssh_timeout=30, on_partial_failure="prompt")
    config = Configuration(products=[product], global_settings=settings)
    
    return config


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""
    
    @patch('src.dagdi.commands.config.validate_configuration')
    @patch('src.dagdi.commands.config.merge_configurations')
    @patch('src.dagdi.commands.config.load_all_configurations')
    def test_workflow_generate_validate_config(self, mock_load, mock_merge, mock_validate):
        """Test workflow: generate → validate configuration."""
        runner = CliRunner()
        
        # Generate template
        result = runner.invoke(app, ["config", "generate"])
        assert result.exit_code == 0
        assert "Template generated" in result.stdout
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_workflow_list_products(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test workflow: list products."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "products"])
        
        assert result.exit_code == 0
        assert "myapp" in result.stdout
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_workflow_list_environments(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test workflow: list environments for product."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "environments", "-p", "myapp"])
        
        assert result.exit_code == 0
        assert "dev" in result.stdout
        assert "prod" in result.stdout
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_workflow_list_servers(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test workflow: list servers in environment."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "servers", "-p", "myapp", "-e", "prod"])
        
        assert result.exit_code == 0
        assert "web-1" in result.stdout
        assert "web-2" in result.stdout
        assert "db-1" in result.stdout
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_workflow_list_services(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test workflow: list services in environment."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config

        import os
        env = os.environ.copy()
        env["COLUMNS"] = "200"
        runner = CliRunner()
        result = runner.invoke(app, ["list", "services", "-p", "myapp", "-e", "prod"], env=env)

        assert result.exit_code == 0
        assert "nginx" in result.stdout
        assert "api" in result.stdout
        assert "postgres" in result.stdout
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_workflow_show_environment(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test workflow: show environment topology."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "show", "-p", "myapp", "-e", "prod"])
        
        assert result.exit_code == 0


class TestContextWorkflow:
    """Test context management workflows."""
    
    @patch('src.dagdi.commands.context.validate_configuration')
    @patch('src.dagdi.commands.context.merge_configurations')
    @patch('src.dagdi.commands.context.load_all_configurations')
    def test_workflow_set_context(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test workflow: set context."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["context", "set", "-p", "myapp", "-e", "prod"])
        
        assert result.exit_code == 0
        assert "set to myapp/prod" in result.stdout
    
    @patch('src.dagdi.commands.context.manager.get_context')
    def test_workflow_get_context(self, mock_get_context):
        """Test workflow: get current context."""
        mock_get_context.return_value = {"product": "myapp", "environment": "prod", "timestamp": "2024-01-01"}

        runner = CliRunner()
        result = runner.invoke(app, ["context", "get"])

        assert result.exit_code == 0
        assert "myapp" in result.stdout
        assert "prod" in result.stdout
    
    @patch('src.dagdi.commands.context.manager.list_contexts')
    @patch('src.dagdi.commands.context.manager.get_current_context_name')
    def test_workflow_list_contexts(self, mock_get_current, mock_list):
        """Test workflow: list saved contexts."""
        mock_list.return_value = {
            "prod": {"product": "myapp", "environment": "prod"},
            "dev": {"product": "myapp", "environment": "dev"}
        }
        mock_get_current.return_value = "prod"
        
        runner = CliRunner()
        result = runner.invoke(app, ["context", "list"])
        
        assert result.exit_code == 0
        assert "prod" in result.stdout
        assert "dev" in result.stdout


class TestErrorScenarios:
    """Test error handling scenarios."""
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_error_missing_product(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test error: missing product."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "environments", "-p", "nonexistent"])
        
        assert result.exit_code == 1
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_error_missing_environment(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test error: missing environment."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "servers", "-p", "myapp", "-e", "nonexistent"])
        
        assert result.exit_code == 1
    
    @patch('src.dagdi.commands.context.manager.get_context')
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_error_missing_context(self, mock_load, mock_merge, mock_validate, mock_get_context):
        """Test error: missing context when required."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_get_context.return_value = None
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "servers"])
        
        assert result.exit_code == 1


class TestCommandCombinations:
    """Test various command combinations."""
    
    @patch('src.dagdi.commands.config.validate_configuration')
    @patch('src.dagdi.commands.config.merge_configurations')
    @patch('src.dagdi.commands.config.load_all_configurations')
    def test_config_commands(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test all config commands."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        
        # Generate
        result = runner.invoke(app, ["config", "generate"])
        assert result.exit_code == 0
        
        # Validate
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        
        # Show settings
        result = runner.invoke(app, ["config", "show-settings"])
        assert result.exit_code == 0
    
    @patch('src.dagdi.commands.discovery.validate_configuration')
    @patch('src.dagdi.commands.discovery.merge_configurations')
    @patch('src.dagdi.commands.discovery.load_all_configurations')
    def test_discovery_commands(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test all discovery commands."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        
        # List products
        result = runner.invoke(app, ["list", "products"])
        assert result.exit_code == 0
        
        # List environments
        result = runner.invoke(app, ["list", "environments", "-p", "myapp"])
        assert result.exit_code == 0
        
        # List servers
        result = runner.invoke(app, ["list", "servers", "-p", "myapp", "-e", "prod"])
        assert result.exit_code == 0
        
        # List services
        result = runner.invoke(app, ["list", "services", "-p", "myapp", "-e", "prod"])
        assert result.exit_code == 0
        
        # Show environment
        result = runner.invoke(app, ["list", "show", "-p", "myapp", "-e", "prod"])
        assert result.exit_code == 0


class TestGlobalFlags:
    """Test global flag handling."""
    
    @patch('src.dagdi.commands.config.validate_configuration')
    @patch('src.dagdi.commands.config.merge_configurations')
    @patch('src.dagdi.commands.config.load_all_configurations')
    def test_global_timeout_flag(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test global --timeout flag."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["--timeout", "60", "config", "validate"])
        
        assert result.exit_code == 0
    
    @patch('src.dagdi.commands.config.validate_configuration')
    @patch('src.dagdi.commands.config.merge_configurations')
    @patch('src.dagdi.commands.config.load_all_configurations')
    def test_global_on_failure_flag(self, mock_load, mock_merge, mock_validate, sample_config):
        """Test global --on-failure flag."""
        mock_load.return_value = [{}]
        mock_merge.return_value = {}
        mock_validate.return_value = sample_config
        
        runner = CliRunner()
        result = runner.invoke(app, ["--on-failure", "continue", "config", "validate"])
        
        assert result.exit_code == 0


class TestHelpAndDocumentation:
    """Test help text and documentation."""
    
    def test_main_help(self):
        """Test main help command."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "Dagdi" in result.stdout
    
    def test_list_help(self):
        """Test list command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["list", "--help"])
        
        assert result.exit_code == 0
    
    def test_manage_help(self):
        """Test manage command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["manage", "--help"])
        
        assert result.exit_code == 0
    
    def test_logs_help(self):
        """Test logs command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--help"])
        
        assert result.exit_code == 0
    
    def test_context_help(self):
        """Test context command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["context", "--help"])
        
        assert result.exit_code == 0
    
    def test_config_help(self):
        """Test config command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["config", "--help"])
        
        assert result.exit_code == 0
    
    def test_top_help(self):
        """Test top command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["top", "--help"])
        
        assert result.exit_code == 0
