"""YAML configuration merging for multiple files."""

import os
from typing import Dict, Any, List, Tuple

from rich.console import Console

_stderr = Console(stderr=True)


class MergeError(Exception):
    """Configuration merge error."""
    pass


def _is_global_settings_file(source: str) -> bool:
    """Check whether a source path looks like a dedicated global-settings file."""
    basename = os.path.basename(source).lower().replace("-", "").replace("_", "")
    return "globalsettings" in basename


def _resolve_global_settings(
    settings_entries: List[Tuple[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Pick the winning global_settings when multiple files define it.

    Rules:
    - 0 files  → empty dict
    - 1 file   → use it
    - N files, exactly 1 is a dedicated global-settings file → use that one,
      warn about the others being ignored
    - N files, 0 or >1 dedicated files → MergeError
    """
    if len(settings_entries) <= 1:
        return settings_entries[0][1] if settings_entries else {}

    standalone = [(src, s) for src, s in settings_entries if _is_global_settings_file(src)]

    if len(standalone) == 1:
        winner_source, winner_settings = standalone[0]
        ignored = [src for src, _ in settings_entries if src != winner_source]
        _stderr.print(
            f"[yellow]Warning:[/yellow] global_settings defined in multiple files. "
            f"Using {winner_source} (dedicated settings file). "
            f"global_settings in {', '.join(ignored)} will be ignored."
        )
        return winner_settings

    if len(standalone) > 1:
        sources = ", ".join(src for src, _ in standalone)
        raise MergeError(
            f"global_settings found in multiple dedicated settings files: "
            f"{sources}. Keep global_settings in exactly one file."
        )

    sources = ", ".join(src for src, _ in settings_entries)
    raise MergeError(
        f"global_settings found in multiple files: {sources}. "
        "Move global_settings to a dedicated file "
        "(e.g. dagdi-globalSettings.yaml or dagdi-<product>-globalSettings.yaml)."
    )


def merge_configurations(configurations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple YAML configurations into a single configuration.

    The same product can be split across multiple files — environments from
    each file are merged together.  Duplicate environment names within the
    same product (across files) raise a MergeError.

    Also merges global services sections from all files, detecting duplicates.

    global_settings must live in exactly one file.  When multiple files define
    it and exactly one of them is a dedicated settings file (filename contains
    "globalSettings"), that file wins and the others are ignored with a warning.

    Args:
        configurations: List of parsed YAML configurations

    Returns:
        Merged configuration dictionary
    """
    merged: Dict[str, Any] = {
        "products": [],
        "services": [],
        "global_settings": {}
    }

    # Track products by name for cross-file environment merging.
    products_by_name: Dict[str, Dict[str, Any]] = {}
    # Track which environments exist per product and which file defined them.
    env_sources: Dict[str, Dict[str, str]] = {}

    # Track services by name to detect duplicates across files
    services_by_name: Dict[str, Dict[str, Any]] = {}
    service_sources: Dict[str, str] = {}

    # Collect all global_settings entries to resolve after the loop.
    global_settings_entries: List[Tuple[str, Dict[str, Any]]] = []

    for index, config in enumerate(configurations):
        source = config.get("__dagdi_source_file", f"<config #{index + 1}>")

        if "global_settings" in config:
            global_settings_entries.append((source, config["global_settings"]))

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

    merged["products"] = list(products_by_name.values())
    merged["services"] = list(services_by_name.values())
    merged["global_settings"] = _resolve_global_settings(global_settings_entries)

    return merged
