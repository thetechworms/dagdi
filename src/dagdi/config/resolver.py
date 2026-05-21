"""Service reference resolution for YAML configuration."""

from copy import deepcopy
from typing import Dict, List
from dagdi.models import Configuration, Service


class ResolutionError(Exception):
    """Service reference resolution error."""
    pass


def resolve_services(config: Configuration) -> Configuration:
    """
    Resolve service_names references to actual Service objects.
    
    For each server with service_names, this function:
    1. Looks up each referenced service in the global services list
    2. Creates a copy of the service (to avoid cross-environment pollution)
    3. Adds the copy to the server's services list
    
    Servers with nested services (old format) are left unchanged.
    Servers with neither nested services nor service_names get an empty services list.
    
    Args:
        config: Configuration object with unresolved service references
        
    Returns:
        Configuration object with resolved services
        
    Raises:
        ResolutionError: If a service reference cannot be resolved
    """
    # Create a map of global services by name for quick lookup
    global_services_map: Dict[str, Service] = {svc.name: svc for svc in config.services}
    
    # Resolve services for each server in each environment in each product
    for product in config.products:
        for environment in product.environments:
            for server in environment.servers:
                # Only resolve if server has service_names (new format)
                if server.service_names:
                    resolved_services: List[Service] = []
                    
                    for service_name in server.service_names:
                        # Look up the service in global services
                        if service_name not in global_services_map:
                            available = ", ".join(sorted(global_services_map.keys())) if global_services_map else "none"
                            raise ResolutionError(
                                f"Cannot resolve service reference '{service_name}' for server '{server.name}' "
                                f"in environment '{environment.name}' (product '{product.name}'). "
                                f"Available global services: {available}"
                            )
                        
                        # Create a copy of the service (deep copy to avoid cross-environment pollution)
                        global_service = global_services_map[service_name]
                        resolved_service = deepcopy(global_service)
                        resolved_services.append(resolved_service)
                    
                    # Replace the server's services list with resolved services
                    server.services = resolved_services
    
    return config
