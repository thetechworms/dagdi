"""Discovery commands for listing products, environments, servers, and services."""

from typing import Optional, List
import typer
from ..config.loader import load_all_configurations, ConfigError
from ..config.merger import merge_configurations
from ..config.validator import validate_configuration, ValidationError
from ..config.resolver import resolve_services
from ..models import Configuration, Product, Environment, Server, Service
from ..context import manager as context_manager
from ..output import formatter

discovery_app = typer.Typer(help="Discovery commands")


def _load_configuration() -> Configuration:
    """
    Load and validate configuration from YAML files.
    
    Returns:
        Configuration object
        
    Raises:
        ConfigError: If configuration cannot be loaded
        ValidationError: If configuration is invalid
    """
    try:
        yaml_configs = load_all_configurations()
        merged = merge_configurations(yaml_configs)
        config = validate_configuration(merged)
        config = resolve_services(config)
        return config
    except (ConfigError, ValidationError) as e:
        raise


@discovery_app.command()
def products() -> None:
    """List all products in the configuration."""
    list_products()


def list_products() -> None:
    """
    List all products in the configuration.
    
    Displays all available products in a formatted table.
    """
    try:
        config = _load_configuration()
        
        if not config.products:
            formatter.format_info("No products found in configuration")
            return
        
        rows = []
        for product in config.products:
            env_names = ", ".join(env.name for env in product.environments) if product.environments else "-"
            rows.append([product.name, env_names])
        formatter.format_table("Products", ["Product Name", "Environments"], rows)
        
    except (ConfigError, ValidationError) as e:
        formatter.format_error(
            "Failed to load configuration",
            str(e),
            suggestion="Check your YAML files in the config/ directory"
        )


@discovery_app.command()
def environments(
    product: Optional[str] = typer.Option(None, "-p", "--product", help="Product name")
) -> None:
    """List all environments for a product."""
    if not list_environments(product):
        raise typer.Exit(1)


@discovery_app.command()
def servers(
    product: Optional[str] = typer.Option(None, "-p", "--product", help="Product name"),
    environment: Optional[str] = typer.Option(None, "-e", "--environment", help="Environment name")
) -> None:
    """List all servers in a product/environment."""
    if not list_servers(product, environment):
        raise typer.Exit(1)


@discovery_app.command()
def services(
    product: Optional[str] = typer.Option(None, "-p", "--product", help="Product name"),
    environment: Optional[str] = typer.Option(None, "-e", "--environment", help="Environment name")
) -> None:
    """List all services in a product/environment."""
    if not list_services(product, environment):
        raise typer.Exit(1)


@discovery_app.command(name="show")
def show(
    product: Optional[str] = typer.Option(None, "-p", "--product", help="Product name"),
    environment: Optional[str] = typer.Option(None, "-e", "--environment", help="Environment name")
) -> None:
    """Show detailed topology of a product/environment."""
    if not show_environment(product, environment):
        raise typer.Exit(1)


def list_environments(product: Optional[str] = None) -> bool:
    """
    List all environments for a product.
    
    Args:
        product: Product name (uses context if not provided)
        
    Raises:
        ConfigError: If configuration cannot be loaded
        ValidationError: If configuration is invalid
    """
    try:
        config = _load_configuration()
        
        # Determine which product to use
        target_product = product
        if not target_product:
            context = context_manager.get_context()
            if not context:
                formatter.format_error(
                    "Missing product context",
                    "No product specified and no context set",
                    suggestion="Run: dagdi context set -p <product> -e <environment>",
                    available_options=[p.name for p in config.products]
                )
                return False
            target_product = context.get('product')
        
        # Find the product
        product_obj = next(
            (p for p in config.products if p.name == target_product),
            None
        )
        
        if not product_obj:
            formatter.format_error(
                "Product not found",
                f"Product '{target_product}' does not exist",
                suggestion="Check the product name and try again",
                available_options=[p.name for p in config.products]
            )
            return False
        
        if not product_obj.environments:
            formatter.format_info(f"No environments found for product '{target_product}'")
            return True
        
        rows = []
        for env in product_obj.environments:
            if not env.servers:
                rows.append([env.name, "-", "-"])
                continue
            for server in env.servers:
                rows.append([env.name, server.name, ", ".join(server.ips)])
        formatter.format_table(
            f"Environments for '{target_product}'",
            ["Environment Name", "Server Name", "IPs"],
            rows
        )
        return True
        
    except (ConfigError, ValidationError) as e:
        formatter.format_error(
            "Failed to load configuration",
            str(e),
            suggestion="Check your YAML files in the config/ directory"
        )
        return False


def list_servers(product: Optional[str] = None, environment: Optional[str] = None) -> bool:
    """
    List all servers in a product/environment.
    
    Args:
        product: Product name (uses context if not provided)
        environment: Environment name (uses context if not provided)
        
    Raises:
        ConfigError: If configuration cannot be loaded
        ValidationError: If configuration is invalid
    """
    try:
        config = _load_configuration()
        
        # Determine which product and environment to use
        target_product = product
        target_environment = environment
        
        if not target_product or not target_environment:
            context = context_manager.get_context()
            if not context:
                formatter.format_error(
                    "Missing context",
                    "Product and/or environment not specified and no context set",
                    suggestion="Run: dagdi context set -p <product> -e <environment>"
                )
                return False
            
            if not target_product:
                target_product = context.get('product')
            if not target_environment:
                target_environment = context.get('environment')
        
        # Find the product
        product_obj = next(
            (p for p in config.products if p.name == target_product),
            None
        )
        
        if not product_obj:
            formatter.format_error(
                "Product not found",
                f"Product '{target_product}' does not exist",
                available_options=[p.name for p in config.products]
            )
            return False
        
        # Find the environment
        env_obj = next(
            (e for e in product_obj.environments if e.name == target_environment),
            None
        )
        
        if not env_obj:
            formatter.format_error(
                "Environment not found",
                f"Environment '{target_environment}' does not exist in product '{target_product}'",
                available_options=[e.name for e in product_obj.environments]
            )
            return False
        
        if not env_obj.servers:
            formatter.format_info(
                f"No servers found for {target_product}/{target_environment}"
            )
            return True
        
        rows = [
            [server.name, server.type, ", ".join(server.ips)]
            for server in env_obj.servers
        ]
        formatter.format_table(
            f"Servers in {target_product}/{target_environment}",
            ["Server Name", "Type", "IPs"],
            rows
        )
        return True
        
    except (ConfigError, ValidationError) as e:
        formatter.format_error(
            "Failed to load configuration",
            str(e),
            suggestion="Check your YAML files in the config/ directory"
        )
        return False


def list_services(product: Optional[str] = None, environment: Optional[str] = None) -> bool:
    """
    List all services in a product/environment.
    
    Args:
        product: Product name (uses context if not provided)
        environment: Environment name (uses context if not provided)
        
    Raises:
        ConfigError: If configuration cannot be loaded
        ValidationError: If configuration is invalid
    """
    try:
        config = _load_configuration()
        
        # Determine which product and environment to use
        target_product = product
        target_environment = environment
        
        if not target_product or not target_environment:
            context = context_manager.get_context()
            if not context:
                formatter.format_error(
                    "Missing context",
                    "Product and/or environment not specified and no context set",
                    suggestion="Run: dagdi context set -p <product> -e <environment>"
                )
                return False
            
            if not target_product:
                target_product = context.get('product')
            if not target_environment:
                target_environment = context.get('environment')
        
        # Find the product
        product_obj = next(
            (p for p in config.products if p.name == target_product),
            None
        )
        
        if not product_obj:
            formatter.format_error(
                "Product not found",
                f"Product '{target_product}' does not exist",
                available_options=[p.name for p in config.products]
            )
            return False
        
        # Find the environment
        env_obj = next(
            (e for e in product_obj.environments if e.name == target_environment),
            None
        )
        
        if not env_obj:
            formatter.format_error(
                "Environment not found",
                f"Environment '{target_environment}' does not exist in product '{target_product}'",
                available_options=[e.name for e in product_obj.environments]
            )
            return False
        
        # Collect all services grouped by server
        rows = []
        for server in env_obj.servers:
            ips = ", ".join(server.ips)
            for idx, service in enumerate(server.services):
                is_first = idx == 0
                rows.append([
                    server.name if is_first else "",
                    ips if is_first else "",
                    service.name,
                    service.friendly_name or "",
                    service.type,
                    service.api_endpoint or "",
                    str(service.port) if service.port is not None else "",
                    service.log_location or "",
                ])

        if not rows:
            formatter.format_info(
                f"No services found for {target_product}/{target_environment}"
            )
            return True

        formatter.format_table(
            f"Services in {target_product}/{target_environment}",
            ["Host Server", "IP", "Service Name", "Friendly Name", "Type",
             "API Endpoint", "Port", "Log Location"],
            rows
        )
        return True
        
    except (ConfigError, ValidationError) as e:
        formatter.format_error(
            "Failed to load configuration",
            str(e),
            suggestion="Check your YAML files in the config/ directory"
        )
        return False


def show_environment(product: Optional[str] = None, environment: Optional[str] = None) -> bool:
    """
    Show detailed topology of a product/environment.
    
    Displays hierarchical structure: Product → Environment → Servers → Services
    
    Args:
        product: Product name (uses context if not provided)
        environment: Environment name (uses context if not provided)
        
    Raises:
        ConfigError: If configuration cannot be loaded
        ValidationError: If configuration is invalid
    """
    try:
        config = _load_configuration()
        
        # Determine which product and environment to use
        target_product = product
        target_environment = environment
        
        if not target_product or not target_environment:
            context = context_manager.get_context()
            if not context:
                formatter.format_error(
                    "Missing context",
                    "Product and/or environment not specified and no context set",
                    suggestion="Run: dagdi context set -p <product> -e <environment>"
                )
                return False
            
            if not target_product:
                target_product = context.get('product')
            if not target_environment:
                target_environment = context.get('environment')
        
        # Find the product
        product_obj = next(
            (p for p in config.products if p.name == target_product),
            None
        )
        
        if not product_obj:
            formatter.format_error(
                "Product not found",
                f"Product '{target_product}' does not exist",
                available_options=[p.name for p in config.products]
            )
            return False
        
        # Find the environment
        env_obj = next(
            (e for e in product_obj.environments if e.name == target_environment),
            None
        )
        
        if not env_obj:
            formatter.format_error(
                "Environment not found",
                f"Environment '{target_environment}' does not exist in product '{target_product}'",
                available_options=[e.name for e in product_obj.environments]
            )
            return False
        
        # Build server data for hierarchical display
        servers_data = [
            {
                'name': server.name,
                'type': server.type,
                'ips': server.ips,
                'services': [
                    {
                        'name': service.name,
                        'friendly_name': service.friendly_name,
                        'type': service.type,
                        'api_endpoint': service.api_endpoint,
                        'port': service.port,
                        'log_location': service.log_location,
                    }
                    for service in server.services
                ]
            }
            for server in env_obj.servers
        ]
        
        formatter.format_hierarchical(target_product, target_environment, servers_data)
        return True
        
    except (ConfigError, ValidationError) as e:
        formatter.format_error(
            "Failed to load configuration",
            str(e),
            suggestion="Check your YAML files in the config/ directory"
        )
        return False
