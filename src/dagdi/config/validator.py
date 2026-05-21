"""YAML configuration validation."""

from copy import deepcopy
from typing import Dict, Any, List, Optional, Set
from dagdi.models import (
    Configuration, Product, Environment, Server, Service, GlobalSettings, SSHConfig
)


class ValidationError(Exception):
    """Configuration validation error."""
    pass


def validate_configuration(config_dict: Dict[str, Any]) -> Configuration:
    """
    Validate and convert a configuration dictionary to Configuration object.
    
    Validates:
    - Required top-level fields: products
    - Product structure: name, environments
    - Environment structure: name, servers
    - Server structure: name, type, ips, ssh (optional)
    - Service structure: name, type (must be systemd or docker)
    - Global services section (optional)
    
    Args:
        config_dict: Parsed YAML configuration dictionary
        
    Returns:
        Validated Configuration object
        
    Raises:
        ValidationError: If configuration is invalid
    """
    errors: List[str] = []
    
    # Check top-level structure
    if not isinstance(config_dict, dict):
        raise ValidationError("Configuration must be a dictionary")
    
    if "products" not in config_dict:
        raise ValidationError("Configuration must contain 'products' field")
    
    if not isinstance(config_dict["products"], list):
        raise ValidationError("'products' must be a list")
    
    if len(config_dict["products"]) == 0:
        raise ValidationError("'products' list cannot be empty")
    
    # Validate global settings first (needed by product/server validation)
    global_settings = GlobalSettings()
    if "global_settings" in config_dict:
        gs_dict = config_dict["global_settings"]
        if isinstance(gs_dict, dict):
            if "ssh_timeout" in gs_dict:
                try:
                    global_settings.ssh_timeout = int(gs_dict["ssh_timeout"])
                except (ValueError, TypeError):
                    raise ValidationError("'global_settings.ssh_timeout' must be an integer")

            if "ssh_port" in gs_dict:
                try:
                    global_settings.ssh_port = int(gs_dict["ssh_port"])
                except (ValueError, TypeError):
                    raise ValidationError("'global_settings.ssh_port' must be an integer")
                if global_settings.ssh_port < 1 or global_settings.ssh_port > 65535:
                    raise ValidationError(
                        "'global_settings.ssh_port' must be between 1 and 65535"
                    )

            if "on_partial_failure" in gs_dict:
                value = gs_dict["on_partial_failure"]
                if value not in ("continue", "stop", "prompt"):
                    raise ValidationError(
                        f"'global_settings.on_partial_failure' must be 'continue', 'stop', or 'prompt', got '{value}'"
                    )
                global_settings.on_partial_failure = value

            if "live_status_table" in gs_dict:
                value = gs_dict["live_status_table"]
                if not isinstance(value, bool):
                    raise ValidationError("'global_settings.live_status_table' must be a boolean")
                global_settings.live_status_table = value

            if "theme" in gs_dict:
                from dagdi.output.themes import AVAILABLE_THEMES
                value = gs_dict["theme"]
                if not isinstance(value, str) or value not in AVAILABLE_THEMES:
                    raise ValidationError(
                        f"'global_settings.theme' must be one of "
                        f"{', '.join(AVAILABLE_THEMES)}, got '{value}'"
                    )
                global_settings.theme = value

            if "log_buffer_size" in gs_dict:
                try:
                    value = int(gs_dict["log_buffer_size"])
                except (ValueError, TypeError):
                    raise ValidationError(
                        "'global_settings.log_buffer_size' must be an integer"
                    )
                if value < 100 or value > 100000:
                    raise ValidationError(
                        "'global_settings.log_buffer_size' must be between 100 and 100000"
                    )
                global_settings.log_buffer_size = value

    # Validate global services (if present)
    global_services = []
    if "services" in config_dict:
        try:
            global_services = _validate_global_services(config_dict["services"])
        except ValidationError as e:
            errors.append(str(e))

    # Validate products
    products = []
    for i, product_dict in enumerate(config_dict["products"]):
        try:
            product = _validate_product(
                product_dict, i, global_services, global_settings
            )
            products.append(product)
        except ValidationError as e:
            errors.append(str(e))

    if errors:
        raise ValidationError("\n".join(errors))

    from dagdi.output.themes import set_theme
    set_theme(global_settings.theme)

    return Configuration(products=products, services=global_services, global_settings=global_settings)


def _validate_global_services(services_list: Any) -> List[Service]:
    """Validate global services section."""
    if not isinstance(services_list, list):
        raise ValidationError("'services' must be a list")
    
    services = []
    service_names_seen: Set[str] = set()
    
    for i, service_dict in enumerate(services_list):
        if not isinstance(service_dict, dict):
            raise ValidationError(f"Service {i} in global services must be a dictionary")
        
        if "name" not in service_dict:
            raise ValidationError(f"Service {i} in global services must have a 'name' field")
        
        service_name = service_dict["name"]
        if not isinstance(service_name, str) or not service_name.strip():
            raise ValidationError(f"Service {i} in global services name must be a non-empty string")
        
        if service_name in service_names_seen:
            raise ValidationError(f"Duplicate service name '{service_name}' in global services section")
        
        service_names_seen.add(service_name)
        
        if "type" not in service_dict:
            raise ValidationError(f"Service '{service_name}' in global services must have a 'type' field")
        
        service_type = service_dict["type"]
        valid_types = ("systemd", "docker")
        if service_type not in valid_types:
            raise ValidationError(
                f"Service '{service_name}' in global services type must be one of {valid_types}, got '{service_type}'"
            )
        
        friendly_name = service_dict.get("friendly_name")
        if friendly_name is not None:
            if not isinstance(friendly_name, str) or not friendly_name.strip():
                raise ValidationError(
                    f"Service '{service_name}' in global services friendly_name must be a non-empty string when provided"
                )
        
        api_endpoint = service_dict.get("api_endpoint")
        if api_endpoint is not None:
            if not isinstance(api_endpoint, str) or not api_endpoint.strip():
                raise ValidationError(
                    f"Service '{service_name}' in global services api_endpoint must be a non-empty string when provided"
                )
        
        port = service_dict.get("port")
        if port is not None:
            try:
                port = int(port)
            except (ValueError, TypeError):
                raise ValidationError(
                    f"Service '{service_name}' in global services port must be an integer when provided"
                )
            if port < 1 or port > 65535:
                raise ValidationError(
                    f"Service '{service_name}' in global services port must be between 1 and 65535"
                )
        
        log_location = service_dict.get("log_location")
        if log_location is not None:
            if not isinstance(log_location, str) or not log_location.strip():
                raise ValidationError(
                    f"Service '{service_name}' in global services log_location must be a non-empty string when provided"
                )
        
        config = {}
        if "config" in service_dict:
            config_dict = service_dict["config"]
            if isinstance(config_dict, dict):
                config = config_dict
        
        service = Service(
            name=service_name,
            type=service_type,
            friendly_name=friendly_name.strip() if isinstance(friendly_name, str) else None,
            api_endpoint=api_endpoint.strip() if isinstance(api_endpoint, str) else None,
            port=port,
            log_location=log_location.strip() if isinstance(log_location, str) else None,
            config=config,
        )
        services.append(service)
    
    return services


def _validate_product(
    product_dict: Dict[str, Any],
    index: int,
    global_services: List[Service],
    global_settings: GlobalSettings = GlobalSettings(),
) -> Product:
    """Validate a product dictionary."""
    if not isinstance(product_dict, dict):
        raise ValidationError(f"Product {index} must be a dictionary")
    
    if "name" not in product_dict:
        raise ValidationError(f"Product {index} must have a 'name' field")
    
    product_name = product_dict["name"]
    if not isinstance(product_name, str) or not product_name.strip():
        raise ValidationError(f"Product {index} name must be a non-empty string")
    
    if "environments" not in product_dict:
        raise ValidationError(f"Product '{product_name}' must have 'environments' field")
    
    if not isinstance(product_dict["environments"], list):
        raise ValidationError(f"Product '{product_name}' environments must be a list")
    
    if len(product_dict["environments"]) == 0:
        raise ValidationError(f"Product '{product_name}' environments list cannot be empty")
    
    # Validate environments
    environments = []
    for i, env_dict in enumerate(product_dict["environments"]):
        try:
            env = _validate_environment(
                env_dict, i, product_name, global_services, global_settings
            )
            environments.append(env)
        except ValidationError as e:
            raise e

    return Product(name=product_name, environments=environments)


def _validate_environment(
    env_dict: Dict[str, Any],
    index: int,
    product_name: str,
    global_services: List[Service],
    global_settings: GlobalSettings = GlobalSettings(),
) -> Environment:
    """Validate an environment dictionary."""
    if not isinstance(env_dict, dict):
        raise ValidationError(f"Environment {index} in product '{product_name}' must be a dictionary")
    
    if "name" not in env_dict:
        raise ValidationError(f"Environment {index} in product '{product_name}' must have a 'name' field")
    
    env_name = env_dict["name"]
    if not isinstance(env_name, str) or not env_name.strip():
        raise ValidationError(f"Environment {index} in product '{product_name}' name must be a non-empty string")
    
    if "servers" not in env_dict:
        raise ValidationError(f"Environment '{env_name}' in product '{product_name}' must have 'servers' field")

    servers_list, default_ssh = _parse_environment_servers(env_dict["servers"], env_name, product_name)
    
    # Validate servers with format consistency check
    servers = []
    format_type = None  # Track format: "nested" or "referenced"
    
    for i, server_dict in enumerate(servers_list):
        try:
            # Detect format before validation
            has_nested = "services" in server_dict
            has_referenced = "service_names" in server_dict
            
            if i == 0:
                # First server determines the format for this environment
                if has_nested:
                    format_type = "nested"
                elif has_referenced:
                    format_type = "referenced"
                # else: format_type remains None (no services at all)
            else:
                # Subsequent servers must use the same format
                if format_type == "nested" and has_referenced and not has_nested:
                    raise ValidationError(
                        f"Environment '{env_name}' in product '{product_name}' mixes old and new formats. "
                        f"Server {i} uses service_names (new format) but earlier servers use nested services (old format). "
                        "Use one format per environment."
                    )
                elif format_type == "referenced" and has_nested and not has_referenced:
                    raise ValidationError(
                        f"Environment '{env_name}' in product '{product_name}' mixes old and new formats. "
                        f"Server {i} uses nested services (old format) but earlier servers use service_names (new format). "
                        "Use one format per environment."
                    )
            
            server = _validate_server(
                server_dict,
                i,
                product_name,
                env_name,
                global_services,
                default_ssh=default_ssh,
                default_port=global_settings.ssh_port,
            )
            servers.append(server)
        except ValidationError as e:
            raise e
    
    return Environment(name=env_name, servers=servers)


def _parse_environment_servers(
    servers_value: Any,
    env_name: str,
    product_name: str,
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Support both legacy list form and mapped form with shared SSH defaults."""
    if isinstance(servers_value, list):
        if len(servers_value) == 0:
            raise ValidationError(f"Environment '{env_name}' in product '{product_name}' servers list cannot be empty")
        return servers_value, None

    if not isinstance(servers_value, dict):
        raise ValidationError(
            f"Environment '{env_name}' in product '{product_name}' servers must be a list or mapping"
        )

    servers_list = servers_value.get("items")
    if not isinstance(servers_list, list):
        raise ValidationError(
            f"Environment '{env_name}' in product '{product_name}' servers.items must be a list"
        )

    if len(servers_list) == 0:
        raise ValidationError(f"Environment '{env_name}' in product '{product_name}' servers.items cannot be empty")

    default_ssh = servers_value.get("ssh")
    if default_ssh is not None and not isinstance(default_ssh, dict):
        raise ValidationError(
            f"Environment '{env_name}' in product '{product_name}' servers.ssh must be a dictionary"
        )

    return servers_list, default_ssh


def _build_ssh_config(
    ssh_dict: Optional[Dict[str, Any]],
    server_name: str,
    product_name: Optional[str] = None,
    env_name: Optional[str] = None,
    sudo_password_prompt_scope: Optional[str] = None,
    default_port: int = 22,
) -> SSHConfig:
    """Build an SSHConfig with validation from a raw dict."""
    ssh_config = SSHConfig(username="ubuntu", port=default_port)
    if not ssh_dict:
        return ssh_config

    if "username" in ssh_dict:
        ssh_config.username = ssh_dict["username"]
    if "password" in ssh_dict:
        ssh_config.password = ssh_dict["password"]
    if "key_path" in ssh_dict:
        ssh_config.key_path = ssh_dict["key_path"]
    if "port" in ssh_dict:
        try:
            ssh_config.port = int(ssh_dict["port"])
        except (ValueError, TypeError):
            raise ValidationError(
                f"Server '{server_name}' ssh port must be an integer"
            )
        if ssh_config.port < 1 or ssh_config.port > 65535:
            raise ValidationError(
                f"Server '{server_name}' ssh port must be between 1 and 65535"
            )
    if "timeout" in ssh_dict:
        try:
            ssh_config.timeout = int(ssh_dict["timeout"])
        except (ValueError, TypeError):
            raise ValidationError(
                f"Server '{server_name}' ssh timeout must be an integer"
            )
    if "sudo" in ssh_dict:
        ssh_config.sudo = bool(ssh_dict["sudo"])
    if "sudo_password" in ssh_dict:
        sudo_password = ssh_dict["sudo_password"]
        if sudo_password == "prompt":
            ssh_config.sudo_password_prompt = True
            if sudo_password_prompt_scope == "environment":
                ssh_config.sudo_password_prompt_cache_key = (
                    f"{product_name}:{env_name}:{ssh_config.username}:shared-sudo-password"
                )
                ssh_config.sudo_password_prompt_label = (
                    f"{product_name}/{env_name} servers ({ssh_config.username})"
                )
            else:
                ssh_config.sudo_password_prompt_cache_key = (
                    f"{product_name}:{env_name}:{server_name}:{ssh_config.username}:sudo-password"
                )
                ssh_config.sudo_password_prompt_label = (
                    f"{ssh_config.username}@{server_name}"
                )
        else:
            ssh_config.sudo_password = sudo_password
    if "sudo_nopasswd" in ssh_dict:
        value = ssh_dict["sudo_nopasswd"]
        if value is None:
            ssh_config.sudo_nopasswd = None
        else:
            ssh_config.sudo_nopasswd = bool(value)

    return ssh_config


def _validate_server(
    server_dict: Dict[str, Any],
    index: int,
    product_name: str,
    env_name: str,
    global_services: List[Service],
    default_ssh: Optional[Dict[str, Any]] = None,
    default_port: int = 22,
) -> Server:
    """Validate a server dictionary."""
    if not isinstance(server_dict, dict):
        raise ValidationError(
            f"Server {index} in environment '{env_name}' (product '{product_name}') must be a dictionary"
        )
    
    if "name" not in server_dict:
        raise ValidationError(
            f"Server {index} in environment '{env_name}' (product '{product_name}') must have a 'name' field"
        )
    
    server_name = server_dict["name"]
    if not isinstance(server_name, str) or not server_name.strip():
        raise ValidationError(
            f"Server {index} in environment '{env_name}' (product '{product_name}') name must be a non-empty string"
        )
    
    if "type" not in server_dict:
        raise ValidationError(
            f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') must have a 'type' field"
        )
    
    server_type = server_dict["type"]
    if not isinstance(server_type, str) or not server_type.strip():
        raise ValidationError(
            f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') type must be a non-empty string"
        )
    
    if "ips" not in server_dict:
        raise ValidationError(
            f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') must have 'ips' field"
        )
    
    ips = server_dict["ips"]
    if not isinstance(ips, list):
        raise ValidationError(
            f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') ips must be a list"
        )
    
    if len(ips) == 0:
        raise ValidationError(
            f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') ips list cannot be empty"
        )
    
    for ip in ips:
        if not isinstance(ip, str) or not ip.strip():
            raise ValidationError(
                f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') all ips must be non-empty strings"
            )
    
    # Validate SSH config
    merged_ssh = deepcopy(default_ssh) if default_ssh else {}
    sudo_password_prompt_scope = None
    if merged_ssh.get("sudo_password") == "prompt":
        sudo_password_prompt_scope = "environment"
    if "ssh" in server_dict:
        ssh_dict = server_dict["ssh"]
        if ssh_dict is not None and not isinstance(ssh_dict, dict):
            raise ValidationError(f"Server '{server_name}' ssh config must be a dictionary")
        if ssh_dict and ssh_dict.get("sudo_password") == "prompt":
            sudo_password_prompt_scope = "server"
        if ssh_dict:
            merged_ssh.update(ssh_dict)
    ssh_config = _build_ssh_config(
        merged_ssh,
        server_name,
        product_name=product_name,
        env_name=env_name,
        sudo_password_prompt_scope=sudo_password_prompt_scope,
        default_port=default_port,
    )
    
    # Validate services and service_names (format detection)
    has_nested_services = "services" in server_dict
    has_service_names = "service_names" in server_dict
    
    # Reject if both are present
    if has_nested_services and has_service_names:
        raise ValidationError(
            f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') "
            "has both nested services and service_names. Choose one format: either define services inline or reference them by name"
        )
    
    services = []
    service_names = []
    
    if has_nested_services:
        # Old format: nested services
        services_list = server_dict["services"]
        if not isinstance(services_list, list):
            raise ValidationError(
                f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') services must be a list"
            )
        
        for i, service_dict in enumerate(services_list):
            try:
                service = _validate_service(service_dict, i, server_name, env_name, product_name)
                services.append(service)
            except ValidationError as e:
                raise e
    
    elif has_service_names:
        # New format: service references
        service_names_list = server_dict["service_names"]
        if not isinstance(service_names_list, list):
            raise ValidationError(
                f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') service_names must be a list"
            )
        
        # Create a map of global service names for quick lookup
        global_service_names = {svc.name for svc in global_services}
        
        for service_name in service_names_list:
            if not isinstance(service_name, str) or not service_name.strip():
                raise ValidationError(
                    f"Server '{server_name}' in environment '{env_name}' (product '{product_name}') "
                    "all service_names must be non-empty strings"
                )
            
            # Validate that the referenced service exists in global services
            if service_name not in global_service_names:
                available = ", ".join(sorted(global_service_names)) if global_service_names else "none"
                raise ValidationError(
                    f"Service '{service_name}' referenced by server '{server_name}' in environment '{env_name}' "
                    f"(product '{product_name}') does not exist in global services. "
                    f"Available services: {available}"
                )
            
            service_names.append(service_name)
    
    return Server(
        name=server_name,
        type=server_type,
        ips=ips,
        ssh_config=ssh_config,
        services=services,
        service_names=service_names
    )


def _validate_service(service_dict: Dict[str, Any], index: int, server_name: str, env_name: str, product_name: str) -> Service:
    """Validate a service dictionary."""
    if not isinstance(service_dict, dict):
        raise ValidationError(
            f"Service {index} on server '{server_name}' in environment '{env_name}' (product '{product_name}') must be a dictionary"
        )
    
    if "name" not in service_dict:
        raise ValidationError(
            f"Service {index} on server '{server_name}' in environment '{env_name}' (product '{product_name}') must have a 'name' field"
        )
    
    service_name = service_dict["name"]
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValidationError(
            f"Service {index} on server '{server_name}' in environment '{env_name}' (product '{product_name}') name must be a non-empty string"
        )
    
    if "type" not in service_dict:
        raise ValidationError(
            f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') must have a 'type' field"
        )
    
    service_type = service_dict["type"]
    valid_types = ("systemd", "docker")
    if service_type not in valid_types:
        raise ValidationError(
            f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') "
            f"type must be one of {valid_types}, got '{service_type}'"
        )

    friendly_name = service_dict.get("friendly_name")
    if friendly_name is not None:
        if not isinstance(friendly_name, str) or not friendly_name.strip():
            raise ValidationError(
                f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') "
                "friendly_name must be a non-empty string when provided"
            )

    api_endpoint = service_dict.get("api_endpoint")
    if api_endpoint is not None:
        if not isinstance(api_endpoint, str) or not api_endpoint.strip():
            raise ValidationError(
                f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') "
                "api_endpoint must be a non-empty string when provided"
            )

    port = service_dict.get("port")
    if port is not None:
        try:
            port = int(port)
        except (ValueError, TypeError):
            raise ValidationError(
                f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') "
                "port must be an integer when provided"
            )
        if port < 1 or port > 65535:
            raise ValidationError(
                f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') "
                "port must be between 1 and 65535"
            )

    log_location = service_dict.get("log_location")
    if log_location is not None:
        if not isinstance(log_location, str) or not log_location.strip():
            raise ValidationError(
                f"Service '{service_name}' on server '{server_name}' in environment '{env_name}' (product '{product_name}') "
                "log_location must be a non-empty string when provided"
            )
    
    # Get service config
    config = {}
    if "config" in service_dict:
        config_dict = service_dict["config"]
        if isinstance(config_dict, dict):
            config = config_dict
    
    return Service(
        name=service_name,
        type=service_type,
        friendly_name=friendly_name.strip() if isinstance(friendly_name, str) else None,
        api_endpoint=api_endpoint.strip() if isinstance(api_endpoint, str) else None,
        port=port,
        log_location=log_location.strip() if isinstance(log_location, str) else None,
        config=config,
    )
