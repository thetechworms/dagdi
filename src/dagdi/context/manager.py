"""Context management operations."""

from typing import Optional, Dict, Any, List
from . import storage
from ..models import Configuration


class ContextError(Exception):
    """Context-related error."""
    pass


def set_context(product: str, environment: str, name: Optional[str] = None) -> str:
    """
    Set the current context to a product and environment.
    
    Args:
        product: Product name
        environment: Environment name
        name: Optional context name (defaults to "{product}-{environment}")
        
    Returns:
        The context name that was set
        
    Raises:
        ContextError: If storage operation fails
    """
    try:
        context_name = storage.set_context(product, environment, name)
        return context_name
    except storage.StorageError as e:
        raise ContextError(f"Failed to set context: {str(e)}")


def get_context() -> Optional[Dict[str, Any]]:
    """
    Get the current context.
    
    Returns:
        Dictionary with 'product', 'environment', 'timestamp' keys
        Returns None if no context is set
        
    Raises:
        ContextError: If storage operation fails
    """
    try:
        return storage.get_current_context()
    except storage.StorageError as e:
        raise ContextError(f"Failed to get context: {str(e)}")


def reset_context() -> None:
    """
    Clear the current context.
    
    Raises:
        ContextError: If storage operation fails
    """
    try:
        storage.reset_context()
    except storage.StorageError as e:
        raise ContextError(f"Failed to reset context: {str(e)}")


def list_contexts() -> Dict[str, Dict[str, Any]]:
    """
    Get all saved contexts.
    
    Returns:
        Dictionary mapping context names to context data
        
    Raises:
        ContextError: If storage operation fails
    """
    try:
        return storage.list_all_contexts()
    except storage.StorageError as e:
        raise ContextError(f"Failed to list contexts: {str(e)}")


def switch_context(name: str) -> None:
    """
    Switch to a different context.
    
    Args:
        name: Name of context to switch to
        
    Raises:
        ContextError: If storage operation fails or context doesn't exist
    """
    try:
        storage.switch_context(name)
    except storage.StorageError as e:
        raise ContextError(f"Failed to switch context: {str(e)}")


def get_current_context_name() -> Optional[str]:
    """
    Get the name of the current context.
    
    Returns:
        Context name or None if no context is set
        
    Raises:
        ContextError: If storage operation fails
    """
    try:
        return storage.get_current_context_name()
    except storage.StorageError as e:
        raise ContextError(f"Failed to get context name: {str(e)}")
