"""Unit tests for command resolver."""

import pytest
from unittest.mock import patch, MagicMock
from src.dagdi.resolver import (
    resolve_scope,
    ResolverError,
    ResolvedScope,
    get_target_ips,
)
from src.dagdi.models import (
    Configuration,
    Product,
    Environment,
    Server,
    Service,
    SSHConfig,
    GlobalSettings,
)


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
    
    # Create services
    nginx = Service(name="nginx", type="systemd", friendly_name="Nginx Web Server")
    postgres = Service(name="postgres", type="systemd")
    api = Service(name="api", type="docker")
    
    # Create servers
    web_server = Server(
        name="web-1",
        type="ubuntu",
        ips=["10.0.1.10", "10.0.1.11"],
        ssh_config=ssh_config,
        services=[nginx, api],
    )
    
    db_server = Server(
        name="db-1",
        type="ubuntu",
        ips=["10.0.2.10"],
        ssh_config=ssh_config,
        services=[postgres],
    )
    
    # Create environment
    dev_env = Environment(name="dev", servers=[web_server, db_server])
    prod_env = Environment(name="prod", servers=[web_server, db_server])
    
    # Create product
    product = Product(name="myapp", environments=[dev_env, prod_env])
    
    # Create configuration
    config = Configuration(
        products=[product],
        global_settings=GlobalSettings(),
    )
    
    return config


class TestResolveScope:
    """Tests for resolve_scope function."""
    
    def test_resolve_scope_with_explicit_product_and_environment(self, sample_config):
        """Should resolve scope with explicit product and environment."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
        )
        
        assert scope.product == "myapp"
        assert scope.environment == "dev"
        assert len(scope.servers) == 2
        assert scope.scope_type == "all_servers"
    
    def test_resolve_scope_with_context(self, sample_config):
        """Should resolve scope using context when flags not provided."""
        with patch('src.dagdi.resolver.context_manager.get_context') as mock_ctx:
            mock_ctx.return_value = {
                "product": "myapp",
                "environment": "dev",
            }
            
            scope = resolve_scope(sample_config)
            
            assert scope.product == "myapp"
            assert scope.environment == "dev"
            assert len(scope.servers) == 2
    
    def test_resolve_scope_missing_context(self, sample_config):
        """Should raise error when context missing and no flags provided."""
        with patch('src.dagdi.resolver.context_manager.get_context') as mock_ctx:
            mock_ctx.return_value = None
            
            with pytest.raises(ResolverError) as exc_info:
                resolve_scope(sample_config)
            
            assert "Product context not set" in str(exc_info.value)
    
    def test_resolve_scope_with_server_filter(self, sample_config):
        """Should resolve scope with specific server."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            server="web-1",
        )
        
        assert scope.product == "myapp"
        assert scope.environment == "dev"
        assert len(scope.servers) == 1
        assert scope.servers[0].name == "web-1"
        assert scope.scope_type == "specific_server"
    
    def test_resolve_scope_with_ip_filter(self, sample_config):
        """Should resolve scope with specific IP."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            ip="10.0.1.10",
        )
        
        assert scope.product == "myapp"
        assert scope.environment == "dev"
        assert len(scope.servers) == 1
        assert scope.servers[0].name == "web-1"
        assert scope.scope_type == "specific_ip"
    
    def test_resolve_scope_with_service_filter(self, sample_config):
        """Should resolve scope with specific service and matching servers only."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            service="nginx",
        )
        
        assert scope.product == "myapp"
        assert scope.environment == "dev"
        assert len(scope.servers) == 1
        assert scope.servers[0].name == "web-1"
        assert scope.services is not None
        assert len(scope.services) == 1
        assert scope.services[0].name == "nginx"
        assert scope.scope_type == "specific_service"

    def test_resolve_scope_with_friendly_service_filter(self, sample_config):
        """Should resolve scope with service friendly name."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            service="Nginx Web Server",
        )

        assert scope.services is not None
        assert len(scope.services) == 1
        assert scope.services[0].name == "nginx"
        assert scope.scope_type == "specific_service"
    
    def test_resolve_scope_with_service_and_server(self, sample_config):
        """Should resolve scope with service on specific server."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            server="web-1",
            service="nginx",
        )
        
        assert scope.product == "myapp"
        assert scope.environment == "dev"
        assert len(scope.servers) == 1
        assert scope.servers[0].name == "web-1"
        assert scope.services is not None
        assert len(scope.services) == 1
        assert scope.services[0].name == "nginx"
        assert scope.scope_type == "specific_service_on_server"
    
    def test_resolve_scope_conflicting_filters(self, sample_config):
        """Should raise error when both --server and --ip provided."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="myapp",
                environment="dev",
                server="web-1",
                ip="10.0.1.10",
            )
        
        assert "Cannot use both --server and --ip" in str(exc_info.value)
    
    def test_resolve_scope_invalid_product(self, sample_config):
        """Should raise error for invalid product."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="nonexistent",
                environment="dev",
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_resolve_scope_invalid_environment(self, sample_config):
        """Should raise error for invalid environment."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="myapp",
                environment="nonexistent",
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_resolve_scope_invalid_server(self, sample_config):
        """Should raise error for invalid server."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="myapp",
                environment="dev",
                server="nonexistent",
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_resolve_scope_invalid_ip(self, sample_config):
        """Should raise error for invalid IP."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="myapp",
                environment="dev",
                ip="192.168.1.1",
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_resolve_scope_invalid_service(self, sample_config):
        """Should raise error for invalid service."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="myapp",
                environment="dev",
                service="nonexistent",
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_resolve_scope_service_not_on_server(self, sample_config):
        """Should raise error when service not on specified server."""
        with pytest.raises(ResolverError) as exc_info:
            resolve_scope(
                sample_config,
                product="myapp",
                environment="dev",
                server="db-1",
                service="nginx",
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_resolve_scope_cli_flags_override_context(self, sample_config):
        """Should use CLI flags instead of context."""
        with patch('src.dagdi.resolver.context_manager.get_context') as mock_ctx:
            mock_ctx.return_value = {
                "product": "other",
                "environment": "staging",
            }
            
            scope = resolve_scope(
                sample_config,
                product="myapp",
                environment="dev",
            )
            
            assert scope.product == "myapp"
            assert scope.environment == "dev"
    
    def test_resolve_scope_partial_context_override(self, sample_config):
        """Should use context for missing flags."""
        with patch('src.dagdi.resolver.context_manager.get_context') as mock_ctx:
            mock_ctx.return_value = {
                "product": "myapp",
                "environment": "dev",
            }
            
            scope = resolve_scope(
                sample_config,
                environment="prod",
            )
            
            assert scope.product == "myapp"
            assert scope.environment == "prod"


class TestGetTargetIps:
    """Tests for get_target_ips function."""
    
    def test_get_target_ips_single_server(self):
        """Should return all IPs from a single server."""
        ssh_config = SSHConfig(username="ubuntu")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10", "10.0.1.11"],
            ssh_config=ssh_config,
        )
        
        targets = get_target_ips([server])
        
        assert len(targets) == 2
        assert targets[0] == (server, "10.0.1.10")
        assert targets[1] == (server, "10.0.1.11")
    
    def test_get_target_ips_multiple_servers(self):
        """Should return all IPs from multiple servers."""
        ssh_config = SSHConfig(username="ubuntu")
        server1 = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
        )
        server2 = Server(
            name="db-1",
            type="ubuntu",
            ips=["10.0.2.10", "10.0.2.11"],
            ssh_config=ssh_config,
        )
        
        targets = get_target_ips([server1, server2])
        
        assert len(targets) == 3
        assert targets[0] == (server1, "10.0.1.10")
        assert targets[1] == (server2, "10.0.2.10")
        assert targets[2] == (server2, "10.0.2.11")
    
    def test_get_target_ips_empty_list(self):
        """Should return empty list for empty servers."""
        targets = get_target_ips([])
        
        assert targets == []


class TestResolvedScope:
    """Tests for ResolvedScope dataclass."""
    
    def test_resolved_scope_creation(self):
        """Should create ResolvedScope with all fields."""
        ssh_config = SSHConfig(username="ubuntu")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
        )
        service = Service(name="nginx", type="systemd")
        
        scope = ResolvedScope(
            product="myapp",
            environment="dev",
            servers=[server],
            services=[service],
            scope_type="specific_service",
        )
        
        assert scope.product == "myapp"
        assert scope.environment == "dev"
        assert len(scope.servers) == 1
        assert len(scope.services) == 1
        assert scope.scope_type == "specific_service"
    
    def test_resolved_scope_default_scope_type(self):
        """Should default scope_type to all_servers."""
        ssh_config = SSHConfig(username="ubuntu")
        server = Server(
            name="web-1",
            type="ubuntu",
            ips=["10.0.1.10"],
            ssh_config=ssh_config,
        )
        
        scope = ResolvedScope(
            product="myapp",
            environment="dev",
            servers=[server],
        )
        
        assert scope.scope_type == "all_servers"


class TestResolverEdgeCases:
    """Tests for edge cases in resolver."""
    
    def test_resolve_scope_multiple_ips_same_server(self, sample_config):
        """Should handle servers with multiple IPs correctly."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            ip="10.0.1.11",
        )
        
        assert len(scope.servers) == 1
        assert scope.servers[0].name == "web-1"
        assert "10.0.1.11" in scope.servers[0].ips
    
    def test_resolve_scope_service_on_multiple_servers(self, sample_config):
        """Should find service across multiple matching servers."""
        # Add api service to db-1 as well
        api = Service(name="api", type="docker")
        sample_config.products[0].environments[0].servers[1].services.append(api)
        
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            service="api",
        )
        
        assert len(scope.servers) == 2
        assert len(scope.services) == 2
        assert all(s.name == "api" for s in scope.services)

    def test_resolve_scope_service_filter_excludes_non_matching_servers(self, sample_config):
        """Should not keep unrelated servers in the execution scope."""
        scope = resolve_scope(
            sample_config,
            product="myapp",
            environment="dev",
            service="api",
        )

        assert [server.name for server in scope.servers] == ["web-1"]
        assert scope.services is not None
        assert [service.name for service in scope.services] == ["api"]
    
    def test_resolve_scope_empty_environment(self):
        """Should handle environment with no servers."""
        ssh_config = SSHConfig(username="ubuntu")
        empty_env = Environment(name="empty", servers=[])
        product = Product(name="myapp", environments=[empty_env])
        config = Configuration(products=[product])
        
        scope = resolve_scope(
            config,
            product="myapp",
            environment="empty",
        )
        
        assert len(scope.servers) == 0
        assert scope.scope_type == "all_servers"
