"""File-based context storage and persistence."""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class StorageError(Exception):
    """Context storage-related error."""
    pass


def get_storage_path() -> Path:
    """
    Get the context storage file path.
    
    Priority:
    1. Project-specific: .dagdi/context.json
    2. Fallback: ~/.dagdi_context
    
    Returns:
        Path object for storage location
    """
    # Check for project-specific storage
    project_storage = Path(".dagdi/context.json")
    if project_storage.exists() or Path(".dagdi").exists():
        return project_storage
    
    # Fallback to home directory
    return Path.home() / ".dagdi_context"


def ensure_storage_dir() -> None:
    """Ensure storage directory exists."""
    storage_path = get_storage_path()
    storage_path.parent.mkdir(parents=True, exist_ok=True)


def load_context_storage() -> Dict[str, Any]:
    """
    Load context storage from file.
    
    Returns:
        Dictionary with 'current' and 'contexts' keys
        Returns empty structure if file doesn't exist
        
    Raises:
        StorageError: If file exists but cannot be read or parsed
    """
    storage_path = get_storage_path()
    
    if not storage_path.exists():
        return {
            "current": None,
            "contexts": {}
        }
    
    try:
        with open(storage_path, 'r') as f:
            content = json.load(f)
            # Ensure required keys exist
            if "current" not in content:
                content["current"] = None
            if "contexts" not in content:
                content["contexts"] = {}
            return content
    except json.JSONDecodeError as e:
        raise StorageError(
            f"Invalid JSON in context storage file {storage_path}:\n{str(e)}"
        )
    except IOError as e:
        raise StorageError(
            f"Cannot read context storage file {storage_path}:\n{str(e)}"
        )


def save_context_storage(data: Dict[str, Any]) -> None:
    """
    Save context storage to file.
    
    Args:
        data: Dictionary with 'current' and 'contexts' keys
        
    Raises:
        StorageError: If file cannot be written
    """
    storage_path = get_storage_path()

    try:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(storage_path, 'w') as f:
            json.dump(data, f, indent=2)
        return
    except OSError as primary_error:
        # If home-based storage is not writable, fallback to project storage.
        project_storage = Path(".dagdi/context.json")
        if storage_path != project_storage:
            try:
                project_storage.parent.mkdir(parents=True, exist_ok=True)
                with open(project_storage, 'w') as f:
                    json.dump(data, f, indent=2)
                return
            except OSError:
                pass

        raise StorageError(
            f"Cannot write to context storage file {storage_path}:\n{str(primary_error)}"
        )


def set_context(product: str, environment: str, name: Optional[str] = None) -> str:
    """
    Set a context and save it to storage.
    
    Args:
        product: Product name
        environment: Environment name
        name: Optional context name (defaults to "{product}-{environment}")
        
    Returns:
        The context name that was set
        
    Raises:
        StorageError: If storage cannot be accessed
    """
    if name is None:
        name = f"{product}-{environment}"
    
    storage = load_context_storage()
    
    storage["contexts"][name] = {
        "product": product,
        "environment": environment,
        "timestamp": datetime.now().isoformat()
    }
    storage["current"] = name
    
    save_context_storage(storage)
    return name


def get_current_context() -> Optional[Dict[str, Any]]:
    """
    Get the current context.
    
    Returns:
        Dictionary with 'product', 'environment', 'timestamp' keys
        Returns None if no context is set
        
    Raises:
        StorageError: If storage cannot be accessed
    """
    storage = load_context_storage()
    
    if storage["current"] is None:
        return None
    
    current_name = storage["current"]
    if current_name not in storage["contexts"]:
        return None
    
    return storage["contexts"][current_name]


def reset_context() -> None:
    """
    Clear the current context.
    
    Raises:
        StorageError: If storage cannot be accessed
    """
    storage = load_context_storage()
    storage["current"] = None
    save_context_storage(storage)


def list_all_contexts() -> Dict[str, Dict[str, Any]]:
    """
    Get all saved contexts.
    
    Returns:
        Dictionary mapping context names to context data
        
    Raises:
        StorageError: If storage cannot be accessed
    """
    storage = load_context_storage()
    return storage["contexts"]


def get_current_context_name() -> Optional[str]:
    """
    Get the name of the current context.
    
    Returns:
        Context name or None if no context is set
        
    Raises:
        StorageError: If storage cannot be accessed
    """
    storage = load_context_storage()
    return storage["current"]


def switch_context(name: str) -> None:
    """
    Switch to a different context.
    
    Args:
        name: Name of context to switch to
        
    Raises:
        StorageError: If storage cannot be accessed or context doesn't exist
    """
    storage = load_context_storage()
    
    if name not in storage["contexts"]:
        available = list(storage["contexts"].keys())
        raise StorageError(
            f"Context '{name}' not found.\n"
            f"Available contexts: {', '.join(available) if available else 'none'}"
        )
    
    storage["current"] = name
    save_context_storage(storage)
