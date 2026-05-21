"""YAML configuration merging for multiple files."""

from typing import Dict, Any, List


class MergeError(Exception):
    """Configuration merge error."""
    pass


def merge_configurations(configurations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple YAML configurations into a single configuration.
    
    Enforces one product definition per file. If the same product appears
    in multiple files, raises a MergeError with source details.
    
    Also merges global services sections from all files, detecting duplicates.
    
    Args:
        configurations: List of parsed YAML configurations
        
    Returns:
        Merged configuration dictionary
    """
    merged = {
        "products": [],
        "services": [],
        "global_settings": {}
    }
    
    # Track products by name to detect duplicates across files.
    products_by_name: Dict[str, Dict[str, Any]] = {}
    product_sources: Dict[str, str] = {}
    
    # Track services by name to detect duplicates across files
    services_by_name: Dict[str, Dict[str, Any]] = {}
    service_sources: Dict[str, str] = {}
    
    for index, config in enumerate(configurations):
        source = config.get("__dagdi_source_file", f"<config #{index + 1}>")

        # Merge global settings (last one wins)
        if "global_settings" in config:
            merged["global_settings"].update(config["global_settings"])
        
        # Collect global services
        for service in config.get("services", []):
            service_name = service.get("name")
            
            if service_name in services_by_name:
                first_source = service_sources[service_name]
                raise MergeError(
                    f"Duplicate service '{service_name}' found in global services sections of multiple files: "
                    f"{first_source}, {source}. "
                    "Define each service in exactly one file."
                )
            
            services_by_name[service_name] = service
            service_sources[service_name] = source
        
        # Collect products
        for product in config.get("products", []):
            product_name = product.get("name")

            if product_name in products_by_name:
                first_source = product_sources[product_name]
                raise MergeError(
                    f"Duplicate product '{product_name}' found in multiple configuration files: "
                    f"{first_source}, {source}. "
                    "Define each product in exactly one file."
                )

            products_by_name[product_name] = product
            product_sources[product_name] = source
    
    merged["products"] = list(products_by_name.values())
    merged["services"] = list(services_by_name.values())
    
    return merged
