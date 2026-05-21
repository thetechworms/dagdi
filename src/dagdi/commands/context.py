"""Context management CLI commands."""

from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel

from ..config.loader import load_all_configurations
from ..config.merger import merge_configurations
from ..config.validator import validate_configuration
from ..config.resolver import resolve_services
from ..context import manager, validator
from ..models import Configuration

_console = Console()

context_app = typer.Typer(help="Context management commands")


def set_context_command(
    product: str,
    environment: str,
    config: Configuration,
    name: Optional[str] = None
) -> str:
    """
    Handle 'dagdi context set' command.
    
    Args:
        product: Product name
        environment: Environment name
        config: Configuration object
        name: Optional context name
        
    Returns:
        Success message
        
    Raises:
        ValueError: If product/environment are invalid
    """
    # Validate context
    try:
        validator.validate_context(product, environment, config)
    except validator.ValidationError as e:
        raise ValueError(str(e))
    
    # Set context
    try:
        context_name = manager.set_context(product, environment, name)
        return f"Context '{context_name}' set to {product}/{environment}"
    except manager.ContextError as e:
        raise ValueError(f"Failed to set context: {str(e)}")


def get_context_command() -> str:
    """
    Handle 'dagdi context get' command.
    
    Returns:
        Current context information
    """
    try:
        context = manager.get_context()
        
        if context is None:
            return "No context set. Use 'dagdi context set -p <product> -e <environment>' to set one."
        
        product = context.get("product", "unknown")
        environment = context.get("environment", "unknown")
        timestamp = context.get("timestamp", "unknown")
        
        return f"Current context: {product}/{environment}\nSet at: {timestamp}"
    except manager.ContextError as e:
        raise ValueError(f"Failed to get context: {str(e)}")


def reset_context_command() -> str:
    """
    Handle 'dagdi context reset' command.
    
    Returns:
        Success message
    """
    try:
        manager.reset_context()
        return "Context reset successfully"
    except manager.ContextError as e:
        raise ValueError(f"Failed to reset context: {str(e)}")


def list_contexts_command() -> str:
    """
    Handle 'dagdi context list' command.
    
    Returns:
        Formatted list of contexts
    """
    try:
        contexts = manager.list_contexts()
        current_name = manager.get_current_context_name()
        
        if not contexts:
            return "No contexts saved yet."
        
        lines = ["Saved contexts:"]
        for name, context in contexts.items():
            product = context.get("product", "unknown")
            environment = context.get("environment", "unknown")
            marker = " (current)" if name == current_name else ""
            lines.append(f"  {name}: {product}/{environment}{marker}")
        
        return "\n".join(lines)
    except manager.ContextError as e:
        raise ValueError(f"Failed to list contexts: {str(e)}")


def switch_context_command(name: str) -> str:
    """
    Handle 'dagdi context switch' command.
    
    Args:
        name: Context name to switch to
        
    Returns:
        Success message
        
    Raises:
        ValueError: If context doesn't exist
    """
    try:
        manager.switch_context(name)
        context = manager.get_context()
        product = context.get("product", "unknown")
        environment = context.get("environment", "unknown")
        return f"Switched to context '{name}': {product}/{environment}"
    except manager.ContextError as e:
        raise ValueError(f"Failed to switch context: {str(e)}")


@context_app.command()
def set(
    product: str = typer.Option(..., "-p", "--product", help="Product name"),
    environment: str = typer.Option(..., "-e", "--environment", help="Environment name"),
    name: Optional[str] = typer.Option(None, "--name", help="Optional context name")
) -> None:
    """Set the current context."""
    try:
        # Load configuration for validation
        yaml_configs = load_all_configurations()
        merged = merge_configurations(yaml_configs)
        config = validate_configuration(merged)
        config = resolve_services(config)
        
        result = set_context_command(product, environment, config, name)
        typer.echo(result)
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


@context_app.command()
def get() -> None:
    """Get the current context."""
    try:
        context = manager.get_context()
        if context is None:
            _console.print(Panel(
                "[dim]No context set.[/dim]\n"
                "Use [cyan]dagdi context set -p <product> -e <environment>[/cyan]",
                title="Current Context",
                border_style="yellow",
            ))
            return
        product = context.get("product", "unknown")
        environment = context.get("environment", "unknown")
        timestamp = context.get("timestamp", "unknown")
        _console.print(Panel(
            f"[bold]{product}[/bold] / [bold]{environment}[/bold]\n"
            f"[dim]Set at: {timestamp}[/dim]",
            title="Current Context",
            border_style="green",
        ))
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


@context_app.command()
def reset() -> None:
    """Reset the current context."""
    try:
        result = reset_context_command()
        typer.echo(result)
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


@context_app.command()
def list() -> None:
    """List all saved contexts."""
    try:
        contexts = manager.list_contexts()
        current_name = manager.get_current_context_name()
        if not contexts:
            _console.print(Panel(
                "[dim]No contexts saved yet.[/dim]",
                title="Saved Contexts",
                border_style="blue",
            ))
            return
        from rich.text import Text
        lines = Text()
        for name, context in contexts.items():
            product = context.get("product", "unknown")
            environment = context.get("environment", "unknown")
            if name == current_name:
                lines.append(f"  {name}: {product}/{environment} ", style="bold")
                lines.append("(current)\n", style="bold green")
            else:
                lines.append(f"  {name}: {product}/{environment}\n")
        _console.print(Panel(lines, title="Saved Contexts", border_style="blue"))
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


@context_app.command()
def switch(name: str = typer.Argument(..., help="Context name to switch to")) -> None:
    """Switch to a saved context."""
    try:
        result = switch_context_command(name)
        typer.echo(result)
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
