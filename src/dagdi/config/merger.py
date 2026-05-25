"""YAML configuration merging for multiple files."""

import os
from typing import Dict, Any, List, Tuple

from rich.console import Console

_stderr = Console(stderr=True)


class MergeError(Exception):
    """Configuration merge error."""
    pass


def merge_configurations(configurations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple YAML configurations into a single configuration.

    The same product can be split across multiple files — environments from
    each file are merged together.  Duplicate environment names within the
    same product (across files) raise a MergeError.

    Also merges global services sections from all files, detecting duplicates.

    Each file's ``global_settings`` is associated with the products defined in
    that file.  If a product is split across several files, at most one of
    them may contain ``global_settings``; otherwise a MergeError is raised.

    Args:
        configurations: List of parsed YAML configurations

    Returns:
        Merged configuration dictionary
    """
    merged: Dict[str, Any] = {
        "products": [],
        "services": [],
    }

    # Track products by name for cross-file environment merging.
    products_by_name: Dict[str, Dict[str, Any]] = {}
    # Track which environments exist per product and which file defined them.
    env_sources: Dict[str, Dict[str, str]] = {}

    # Track services by name to detect duplicates across files
    services_by_name: Dict[str, Dict[str, Any]] = {}
    service_sources: Dict[str, str] = {}

    # Track which files supply global_settings for each product.
    product_settings_sources: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}

    for index, config in enumerate(configurations):
        source = config.get("__dagdi_source_file", f"<config #{index + 1}>")

        file_settings = config.get("global_settings")

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

        # Collect and merge products
        for product in config.get("products", []):
            product_name = product.get("name")
            environments = product.get("environments", [])

            if file_settings is not None:
                product_settings_sources.setdefault(product_name, []).append(
                    (source, file_settings)
                )

            if product_name not in products_by_name:
                products_by_name[product_name] = product
                env_sources[product_name] = {}
                for env in environments:
                    env_name = env.get("name")
                    env_sources[product_name][env_name] = source
            else:
                for env in environments:
                    env_name = env.get("name")
                    if env_name in env_sources[product_name]:
                        first_source = env_sources[product_name][env_name]
                        raise MergeError(
                            f"Duplicate environment '{env_name}' for product "
                            f"'{product_name}' found in multiple files: "
                            f"{first_source}, {source}. "
                            "Define each environment in exactly one file."
                        )
                    env_sources[product_name][env_name] = source
                products_by_name[product_name]["environments"].extend(environments)

    # Embed per-product global_settings into product dicts.
    for product_name, entries in product_settings_sources.items():
        if len(entries) > 1:
            sources = ", ".join(src for src, _ in entries)
            raise MergeError(
                f"global_settings for product '{product_name}' found in multiple files: "
                f"{sources}. "
                "Define global_settings in exactly one file per product."
            )
        if product_name in products_by_name:
            products_by_name[product_name]["global_settings"] = entries[0][1]

    merged["products"] = list(products_by_name.values())
    merged["services"] = list(services_by_name.values())

    return merged
