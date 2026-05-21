"""YAML configuration file discovery and loading."""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml


class ConfigError(Exception):
    """Configuration-related error."""
    pass


def get_default_config_dir() -> Path:
    """
    Resolve the default config directory for CLI usage.

    Priority:
    1. ~/.config/dagdi (default well-known location)
    2. DAGDI_CONFIG_DIR environment variable (override if default not found)
    """
    default_dir = Path.home() / ".config" / "dagdi"
    if default_dir.exists():
        return default_dir

    env_config_dir = os.environ.get("DAGDI_CONFIG_DIR")
    if env_config_dir:
        return Path(env_config_dir).expanduser()

    return default_dir


def discover_yaml_files(config_dir: Optional[Path] = None) -> List[Path]:
    """
    Discover all YAML configuration files in the config directory.
    
    Looks for files matching patterns: dagdi-*.yaml or dagdi-*.yml
    
    Args:
        config_dir: Path to configuration directory.
                    If None, resolves using get_default_config_dir()
        
    Returns:
        List of Path objects for discovered YAML files, sorted
        
    Raises:
        ConfigError: If config directory doesn't exist or no files found
    """
    resolved_config_dir = get_default_config_dir() if config_dir is None else config_dir

    if not resolved_config_dir.exists():
        default_dir = Path.home() / ".config" / "dagdi"
        raise ConfigError(
            f"Config directory not found: {resolved_config_dir}\n"
            f"Create your config at {default_dir} (default location):\n"
            f"  mkdir -p {default_dir}\n"
            f"  dagdi config generate\n"
            f"Or set DAGDI_CONFIG_DIR to use a custom location:\n"
            f"  export DAGDI_CONFIG_DIR=/path/to/your/config"
        )
    
    # Find all matching YAML files
    files = list(resolved_config_dir.glob("dagdi-*.yaml"))
    files.extend(resolved_config_dir.glob("dagdi-*.yml"))
    
    if not files:
        raise ConfigError(
            f"No YAML configuration files found in {resolved_config_dir}\n"
            f"Expected files matching: dagdi-*.yaml or dagdi-*.yml\n"
            f"You can generate a template with: dagdi config generate"
        )
    
    return sorted(files)


def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """
    Load a single YAML file.
    
    Args:
        file_path: Path to YAML file
        
    Returns:
        Parsed YAML content as dictionary
        
    Raises:
        ConfigError: If file cannot be read or YAML is invalid
    """
    try:
        with open(file_path, 'r') as f:
            content = yaml.safe_load(f)
            if content is None:
                content = {}
            return content
    except yaml.YAMLError as e:
        raise ConfigError(
            f"Invalid YAML syntax in {file_path.name}:\n{str(e)}"
        )
    except IOError as e:
        raise ConfigError(
            f"Cannot read configuration file {file_path.name}:\n{str(e)}"
        )


def load_all_configurations(config_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load all YAML configuration files from the config directory.
    
    Args:
        config_dir: Path to configuration directory.
                    If None, resolves using get_default_config_dir()
        
    Returns:
        List of parsed YAML configurations
        
    Raises:
        ConfigError: If discovery or loading fails
    """
    files = discover_yaml_files(config_dir)
    configurations = []
    
    for file_path in files:
        config = load_yaml_file(file_path)
        # Keep source metadata for downstream merge/validation errors.
        if isinstance(config, dict):
            config["__dagdi_source_file"] = str(file_path)
        configurations.append(config)
    
    return configurations
