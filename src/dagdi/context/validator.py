"""Context validation functions."""

from typing import Optional, List
from ..models import Configuration


class ValidationError(Exception):
    """Context validation error."""
    pass


def validate_product_exists(product: str, config: Configuration) -> None:
    """
    Validate that a product exists in the configuration.
    
    Args:
        product: Product name to validate
        config: Configuration object
        
    Raises:
        ValidationError: If product doesn't exist
    """
    product_names = [p.name for p in config.products]
    
    if product not in product_names:
        available = ", ".join(product_names) if product_names else "none"
        raise ValidationError(
            f"Product '{product}' not found in configuration.\n"
            f"Available products: {available}"
        )


def validate_environment_exists(
    product: str, 
    environment: str, 
    config: Configuration
) -> None:
    """
    Validate that an environment exists in a product.
    
    Args:
        product: Product name
        environment: Environment name to validate
        config: Configuration object
        
    Raises:
        ValidationError: If product or environment doesn't exist
    """
    # First validate product exists
    validate_product_exists(product, config)
    
    # Find the product
    product_obj = next((p for p in config.products if p.name == product), None)
    if product_obj is None:
        raise ValidationError(f"Product '{product}' not found")
    
    env_names = [e.name for e in product_obj.environments]
    
    if environment not in env_names:
        available = ", ".join(env_names) if env_names else "none"
        raise ValidationError(
            f"Environment '{environment}' not found in product '{product}'.\n"
            f"Available environments: {available}"
        )


def validate_context(
    product: str,
    environment: str,
    config: Configuration
) -> None:
    """
    Validate a complete context (product + environment).
    
    Args:
        product: Product name
        environment: Environment name
        config: Configuration object
        
    Raises:
        ValidationError: If context is invalid
    """
    validate_environment_exists(product, environment, config)


def get_available_products(config: Configuration) -> List[str]:
    """
    Get list of available product names.
    
    Args:
        config: Configuration object
        
    Returns:
        List of product names
    """
    return [p.name for p in config.products]


def get_available_environments(product: str, config: Configuration) -> List[str]:
    """
    Get list of available environment names for a product.
    
    Args:
        product: Product name
        config: Configuration object
        
    Returns:
        List of environment names
        
    Raises:
        ValidationError: If product doesn't exist
    """
    validate_product_exists(product, config)
    
    product_obj = next((p for p in config.products if p.name == product), None)
    if product_obj is None:
        raise ValidationError(f"Product '{product}' not found")
    
    return [e.name for e in product_obj.environments]
