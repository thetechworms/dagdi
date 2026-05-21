"""Command resolver for scope resolution and context application."""

from typing import Optional, List, Tuple, Literal
from dataclasses import dataclass
from .models import Configuration, Server, Service
from .context import manager as context_manager
from .context import validator as context_validator


class ResolverError(Exception):
    """Resolver-related error."""
    pass


@dataclass
class ResolvedScope:
    """Result of scope resolution."""
    
    product: str
    environment: str
    servers: List[Server]
    services: Optional[List[Service]] = None
    scope_type: Literal[
        "all_servers",
        "all_services",
        "specific_server",
        "specific_ip",
        "specific_service",
        "specific_service_on_server"
    ] = "all_servers"


def resolve_scope(
    config: Configuration,
    product: Optional[str] = None,
    environment: Optional[str] = None,
    server: Optional[str] = None,
    ip: Optional[str] = None,
    service: Optional[str] = None,
) -> ResolvedScope:
    """
    Resolve command scope based on context and CLI flags.
    
    Determines which servers/services to target based on:
    1. Context (product + environment)
    2. CLI flags (--server, --ip, -p, -e)
    3. Command requirements
    
    Resolution Priority:
    - CLI flags override context
    - Flags must be valid (exist in configuration)
    - Conflicting flags (--server + --ip) are rejected
    
    Args:
        config: Configuration object
        product: Product name (from -p flag or context)
        environment: Environment name (from -e flag or context)
        server: Server name (from --server flag)
        ip: IP address (from --ip flag)
        service: Service name (from command argument)
        
    Returns:
        ResolvedScope with product, environment, servers, and scope_type
        
    Raises:
        ResolverError: If scope cannot be resolved or is invalid
    """
    
    # Check for conflicting filters
    if server is not None and ip is not None:
        raise ResolverError(
            "Cannot use both --server and --ip flags together.\n"
            "Please specify only one filter."
        )
    
    # Apply context if flags not provided
    if product is None or environment is None:
        current_context = context_manager.get_context()
        
        if product is None:
            if current_context is None:
                raise ResolverError(
                    "Product context not set.\n"
                    "Please set context with: dagdi context set -p <product> -e <environment>\n"
                    "Or use -p flag to override."
                )
            product = current_context["product"]
        
        if environment is None:
            if current_context is None:
                raise ResolverError(
                    "Environment context not set.\n"
                    "Please set context with: dagdi context set -p <product> -e <environment>\n"
                    "Or use -e flag to override."
                )
            environment = current_context["environment"]
    
    # Validate product and environment exist
    try:
        context_validator.validate_environment_exists(product, environment, config)
    except context_validator.ValidationError as e:
        raise ResolverError(str(e))
    
    # Find the product and environment
    product_obj = next((p for p in config.products if p.name == product), None)
    if product_obj is None:
        raise ResolverError(f"Product '{product}' not found in configuration")
    
    env_obj = next((e for e in product_obj.environments if e.name == environment), None)
    if env_obj is None:
        raise ResolverError(
            f"Environment '{environment}' not found in product '{product}'"
        )
    
    # Resolve servers based on filters
    if server is not None:
        # Specific server by name
        servers = _resolve_server_by_name(server, env_obj)
        if not servers:
            raise ResolverError(
                f"Server '{server}' not found in {product}/{environment}"
            )
        scope_type = "specific_server"
    elif ip is not None:
        # Specific IP address
        servers = _resolve_server_by_ip(ip, env_obj)
        if not servers:
            raise ResolverError(
                f"IP '{ip}' not found in {product}/{environment}"
            )
        scope_type = "specific_ip"
    else:
        # All servers in environment
        servers = env_obj.servers
        scope_type = "all_servers"
    
    # Resolve services if specified
    services = None
    if service is not None:
        services = _resolve_services(service, servers)
        if not services:
            raise ResolverError(
                f"Service '{service}' not found on target servers"
            )

        # Narrow execution targets to only the servers that actually host the
        # requested service. This prevents service commands from reporting
        # "not found" failures on unrelated servers in the same environment.
        servers = [srv for srv in servers if _server_has_service(srv, service)]
        
        if server is not None or ip is not None:
            scope_type = "specific_service_on_server"
        else:
            scope_type = "specific_service"
    
    return ResolvedScope(
        product=product,
        environment=environment,
        servers=servers,
        services=services,
        scope_type=scope_type,
    )


def _resolve_server_by_name(server_name: str, env_obj) -> List[Server]:
    """
    Find servers by name.
    
    Args:
        server_name: Name of server to find
        env_obj: Environment object
        
    Returns:
        List of matching servers (0 or 1 element)
    """
    matching = [s for s in env_obj.servers if s.name == server_name]
    return matching


def _resolve_server_by_ip(ip: str, env_obj) -> List[Server]:
    """
    Find servers by IP address.
    
    Args:
        ip: IP address to find
        env_obj: Environment object
        
    Returns:
        List of servers containing the IP
    """
    matching = [s for s in env_obj.servers if ip in s.ips]
    return matching


def _resolve_services(service_name: str, servers: List[Server]) -> List[Service]:
    """
    Find services by name across servers.
    
    Args:
        service_name: Name of service to find
        servers: List of servers to search
        
    Returns:
        List of matching services
    """
    services = []
    for server in servers:
        for svc in server.services:
            if _service_matches(svc, service_name):
                services.append(svc)
    return services


def _service_matches(service_obj: Service, identifier: str) -> bool:
    """Return True when a service matches a CLI identifier."""
    service_key = identifier.strip().lower()
    friendly_key = (service_obj.friendly_name or "").strip().lower()
    return service_obj.name == identifier or friendly_key == service_key


def _server_has_service(server: Server, service_name: str) -> bool:
    """Return True when the server contains a matching service."""
    return any(_service_matches(service_obj, service_name) for service_obj in server.services)


def get_target_ips(servers: List[Server]) -> List[Tuple[Server, str]]:
    """
    Get all target IPs from servers.
    
    Args:
        servers: List of servers
        
    Returns:
        List of (server, ip) tuples
    """
    targets = []
    for server in servers:
        for ip in server.ips:
            targets.append((server, ip))
    return targets
