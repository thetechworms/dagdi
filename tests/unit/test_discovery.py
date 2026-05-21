"""Unit tests for discovery commands."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from dagdi.commands import discovery
from dagdi.models import (
    Configuration, Product, Environment, Server, Service, SSHConfig, Context
)
from dagdi.config.loader import ConfigError
from dagdi.config.validator import ValidationError


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
    
    service1 = Service(name="nginx", type="systemd")
    service2 = Service(name="api", type="docker")
    
    server1 = Server(
        name="web-1",
        type="ubuntu",
        ips=["10.0.1.10", "10.0.1.11"],
        ssh_config=ssh_config,
        services=[service1, service2]
    )
    
    service3 = Service(name="postgres", type="systemd")
    server2 = Server(
        name="db-1",
        type="ubuntu",
        ips=["10.0.2.10"],
        ssh_config=ssh_config,
        services=[service3]
    )
    
    env_dev = Environment(name="dev", servers=[server1, server2])
    env_prod = Environment(name="prod", servers=[server1])
    
    product1 = Product(name="myapp", environments=[env_dev, env_prod])
    product2 = Product(name="otherapp", environments=[env_dev])
    
    return Configuration(products=[product1, product2])


@pytest.fixture
def empty_config():
    """Create an empty configuration."""
    return Configuration(products=[])


class TestListProducts:
    """Tests for list_products command."""
    
    def test_list_products_success(self, sample_config, capsys):
        """Test listing products successfully."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_products()
            captured = capsys.readouterr()
            assert "myapp" in captured.out
            assert "otherapp" in captured.out
    
    def test_list_products_empty(self, empty_config, capsys):
        """Test listing products when none exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=empty_config):
            discovery.list_products()
            captured = capsys.readouterr()
            assert "No products found" in captured.out
    
    def test_list_products_config_error(self, capsys):
        """Test handling of configuration error."""
        with patch('dagdi.commands.discovery._load_configuration', 
                   side_effect=ConfigError("Config not found")):
            discovery.list_products()
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Failed to load configuration" in captured.out


class TestListEnvironments:
    """Tests for list_environments command."""
    
    def test_list_environments_with_product_flag(self, sample_config, capsys):
        """Test listing environments with -p flag."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_environments(product="myapp")
            captured = capsys.readouterr()
            assert "dev" in captured.out
            assert "prod" in captured.out
    
    def test_list_environments_with_context(self, sample_config, capsys):
        """Test listing environments using context."""
        context = {"product": "myapp", "environment": "dev"}
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=context):
                discovery.list_environments()
                captured = capsys.readouterr()
                assert "dev" in captured.out
                assert "prod" in captured.out
    
    def test_list_environments_no_context_no_product(self, sample_config, capsys):
        """Test error when no context and no product flag."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=None):
                discovery.list_environments()
                captured = capsys.readouterr()
                assert "ERROR" in captured.out
                assert "Missing product context" in captured.out
    
    def test_list_environments_product_not_found(self, sample_config, capsys):
        """Test error when product doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_environments(product="nonexistent")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Product not found" in captured.out
    
    def test_list_environments_empty(self, sample_config, capsys):
        """Test listing environments when product has none."""
        empty_product = Product(name="empty", environments=[])
        config = Configuration(products=[empty_product])
        
        with patch('dagdi.commands.discovery._load_configuration', return_value=config):
            discovery.list_environments(product="empty")
            captured = capsys.readouterr()
            assert "No environments found" in captured.out


class TestListServers:
    """Tests for list_servers command."""
    
    def test_list_servers_with_flags(self, sample_config, capsys):
        """Test listing servers with -p and -e flags."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_servers(product="myapp", environment="dev")
            captured = capsys.readouterr()
            assert "web-1" in captured.out
            assert "db-1" in captured.out
            assert "10.0.1.10" in captured.out
    
    def test_list_servers_with_context(self, sample_config, capsys):
        """Test listing servers using context."""
        context = {"product": "myapp", "environment": "dev"}
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=context):
                discovery.list_servers()
                captured = capsys.readouterr()
                assert "web-1" in captured.out
                assert "db-1" in captured.out
    
    def test_list_servers_no_context(self, sample_config, capsys):
        """Test error when no context and no flags."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=None):
                discovery.list_servers()
                captured = capsys.readouterr()
                assert "ERROR" in captured.out
                assert "Missing context" in captured.out
    
    def test_list_servers_product_not_found(self, sample_config, capsys):
        """Test error when product doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_servers(product="nonexistent", environment="dev")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Product not found" in captured.out
    
    def test_list_servers_environment_not_found(self, sample_config, capsys):
        """Test error when environment doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_servers(product="myapp", environment="nonexistent")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Environment not found" in captured.out
    
    def test_list_servers_empty(self, sample_config, capsys):
        """Test listing servers when environment has none."""
        env = Environment(name="empty", servers=[])
        product = Product(name="test", environments=[env])
        config = Configuration(products=[product])
        
        with patch('dagdi.commands.discovery._load_configuration', return_value=config):
            discovery.list_servers(product="test", environment="empty")
            captured = capsys.readouterr()
            assert "No servers found" in captured.out


class TestListServices:
    """Tests for list_services command."""
    
    def test_list_services_with_flags(self, sample_config, capsys):
        """Test listing services with -p and -e flags."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_services(product="myapp", environment="dev")
            captured = capsys.readouterr()
            assert "nginx" in captured.out
            assert "api" in captured.out
            assert "postg" in captured.out
            assert "system" in captured.out
            assert "docker" in captured.out
            assert "web-1" in captured.out
            assert "db-1" in captured.out
            assert "10.0.1" in captured.out
            assert "10.0.2" in captured.out
    
    def test_list_services_with_context(self, sample_config, capsys):
        """Test listing services using context."""
        context = {"product": "myapp", "environment": "dev"}
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=context):
                discovery.list_services()
                captured = capsys.readouterr()
                assert "nginx" in captured.out
                assert "api" in captured.out
    
    def test_list_services_no_context(self, sample_config, capsys):
        """Test error when no context and no flags."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=None):
                discovery.list_services()
                captured = capsys.readouterr()
                assert "ERROR" in captured.out
                assert "Missing context" in captured.out
    
    def test_list_services_product_not_found(self, sample_config, capsys):
        """Test error when product doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_services(product="nonexistent", environment="dev")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Product not found" in captured.out
    
    def test_list_services_environment_not_found(self, sample_config, capsys):
        """Test error when environment doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.list_services(product="myapp", environment="nonexistent")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Environment not found" in captured.out
    
    def test_list_services_empty(self, sample_config, capsys):
        """Test listing services when environment has none."""
        server = Server(
            name="empty-server",
            type="ubuntu",
            ips=["10.0.1.1"],
            ssh_config=SSHConfig(username="ubuntu"),
            services=[]
        )
        env = Environment(name="empty", servers=[server])
        product = Product(name="test", environments=[env])
        config = Configuration(products=[product])
        
        with patch('dagdi.commands.discovery._load_configuration', return_value=config):
            discovery.list_services(product="test", environment="empty")
            captured = capsys.readouterr()
            assert "No services found" in captured.out


class TestShowEnvironment:
    """Tests for show_environment command."""
    
    def test_show_environment_with_flags(self, sample_config, capsys):
        """Test showing environment with -p and -e flags."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.show_environment(product="myapp", environment="dev")
            captured = capsys.readouterr()
            assert "myapp" in captured.out
            assert "dev" in captured.out
            assert "web-1" in captured.out
            assert "db-1" in captured.out
            assert "nginx" in captured.out
            assert "postgres" in captured.out
    
    def test_show_environment_with_context(self, sample_config, capsys):
        """Test showing environment using context."""
        context = {"product": "myapp", "environment": "dev"}
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=context):
                discovery.show_environment()
                captured = capsys.readouterr()
                assert "myapp" in captured.out
                assert "dev" in captured.out
    
    def test_show_environment_no_context(self, sample_config, capsys):
        """Test error when no context and no flags."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            with patch('dagdi.context.manager.get_context', return_value=None):
                discovery.show_environment()
                captured = capsys.readouterr()
                assert "ERROR" in captured.out
                assert "Missing context" in captured.out
    
    def test_show_environment_product_not_found(self, sample_config, capsys):
        """Test error when product doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.show_environment(product="nonexistent", environment="dev")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Product not found" in captured.out
    
    def test_show_environment_environment_not_found(self, sample_config, capsys):
        """Test error when environment doesn't exist."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.show_environment(product="myapp", environment="nonexistent")
            captured = capsys.readouterr()
            assert "ERROR" in captured.out
            assert "Environment not found" in captured.out
    
    def test_show_environment_hierarchical_structure(self, sample_config, capsys):
        """Test that hierarchical structure is displayed correctly."""
        with patch('dagdi.commands.discovery._load_configuration', return_value=sample_config):
            discovery.show_environment(product="myapp", environment="dev")
            captured = capsys.readouterr()

            assert "myapp" in captured.out
            assert "dev" in captured.out
            assert "web-1" in captured.out
            assert "Services" in captured.out
