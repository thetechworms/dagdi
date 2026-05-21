"""Configuration management commands."""

from pathlib import Path
from typing import Optional
import typer
from dagdi.config.loader import (
    load_all_configurations,
    ConfigError,
    get_default_config_dir,
)
from dagdi.config.merger import merge_configurations
from dagdi.config.validator import validate_configuration, ValidationError
from dagdi.config.resolver import resolve_services


app = typer.Typer(help="Configuration management commands")


TEMPLATE_CONTENT = """# Dagdi Configuration Template
# This file defines your infrastructure topology

products:
  - name: myapp
    environments:
      - name: dev
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
            # port: 2222            # SSH port (overrides global ssh_port, default: 22)
            timeout: 30
          items:
            - name: web-1
              type: ubuntu
              ips:
                - 10.0.1.10
              services:
                - name: nginx
                  friendly_name: Nginx Web Server
                  type: systemd
                  port: 80
                  log_location: /var/log/nginx
                - name: api
                  friendly_name: Application API
                  type: docker
                  api_endpoint: http://10.0.1.10:8080/health
                  port: 8080
                  log_location: /var/log/myapp-api
                  config:
                    container_name: myapp-api
            - name: db-1
              type: ubuntu
              ips:
                - 10.0.2.10
              services:
                - name: postgres
                  type: systemd
      
      - name: staging
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
          items:
            - name: web-staging
              type: ubuntu
              ips:
                - 10.1.1.10
              services:
                - name: nginx
                  type: systemd
                - name: api
                  type: docker
                  config:
                    container_name: myapp-api-staging
            - name: db-staging
              type: ubuntu
              ips:
                - 10.1.2.10
              services:
                - name: postgres
                  type: systemd
      
      - name: prod
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
            # port: 2222            # SSH port (overrides global ssh_port, default: 22)
            timeout: 30
          items:
            - name: web-prod-1
              type: ubuntu
              ips:
                - 10.2.1.10
                - 10.2.1.11
              services:
                - name: nginx
                  type: systemd
                - name: api
                  type: docker
                  config:
                    container_name: myapp-api
            - name: web-prod-2
              type: ubuntu
              ips:
                - 10.2.1.20
                - 10.2.1.21
              services:
                - name: nginx
                  type: systemd
                - name: api
                  type: docker
                  config:
                    container_name: myapp-api
            - name: db-prod
              type: ubuntu
              ips:
                - 10.2.2.10
              services:
                - name: postgres
                  type: systemd

# Global settings (optional)
global_settings:
  ssh_timeout: 30
  ssh_port: 22                # Default SSH port for all servers (override per server)
  on_partial_failure: prompt  # Options: continue, stop, prompt
  live_status_table: false    # Feature flag: stream status table while checks run
  theme: default              # Color theme: default, light, dark, no_color

# Configuration Guide:
# 
# products:
#   - name: <product_name>          # Name of your product/application
#     environments:
#       - name: <env_name>          # Environment name (dev, staging, prod, etc.)
#         servers:
#           ssh:                    # Optional shared SSH defaults for all servers in this environment
#             username: <user>      # SSH username
#             key_path: <path>      # Path to SSH private key
#             port: <number>        # SSH port (default: from global_settings.ssh_port or 22)
#             timeout: <seconds>    # SSH timeout in seconds
#             sudo: <true/false>    # Whether to use sudo
#             sudo_nopasswd: <true/false>  # Optional override for passwordless sudo detection
#           items:
#             - name: <server_name> # Unique server name
#               type: <os_type>     # OS type (ubuntu, centos, etc.)
#               ips:
#                 - <ip_address>    # One or more IP addresses
#               ssh:                # Optional per-server override of shared SSH config
#                 port: <number>    # SSH port (overrides env-level and global)
#                 timeout: <seconds>
#               services:
#                 - name: <svc_name>  # Service name
#                   friendly_name: <display_name>  # Friendly display name (optional)
#                   api_endpoint: <url>  # Optional API endpoint
#                   port: <number>  # Optional port (1-65535)
#                   log_location: <path>  # Optional log location path
#                   type: <type>      # Service type: systemd or docker
#                   config:           # Service-specific configuration
#                     container_name: <name>  # For docker services
#
# Service Types:
#   - systemd: Linux systemd services (e.g., nginx, postgres)
#   - docker: Docker containers
#
# Global Settings:
#   ssh_timeout: Default SSH timeout in seconds (default: 30)
#   ssh_port: Default SSH port for all servers (default: 22, override per server)
#   on_partial_failure: Behavior when some targets fail
#     - prompt: Ask user whether to continue (default)
#     - continue: Continue with remaining targets
#     - stop: Stop on first failure
#   live_status_table: Enable live/incremental status table rendering (default: false)
#   theme: Color theme for CLI output (default, light, dark, no_color)
"""


def generate_template(config_dir: Optional[Path] = None) -> Path:
    """
    Generate a template YAML configuration file.
    
    Creates `dagdi-template.yaml` in the config directory with example
    products, environments, servers, and services.
    
    Args:
        config_dir: Path to configuration directory.
                    If None, resolves using get_default_config_dir()
    """
    target_dir = get_default_config_dir() if config_dir is None else config_dir

    # Create config directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)
    
    template_path = target_dir / "dagdi-template.yaml"
    
    # Write template file
    with open(template_path, 'w') as f:
        f.write(TEMPLATE_CONTENT)

    return template_path


@app.command()
def generate() -> None:
    """Generate a template YAML configuration file."""
    try:
        template_path = generate_template()
        typer.echo(f"✓ Template generated: {template_path}")
        typer.echo("  Edit this file with your infrastructure details")
        typer.echo("  Then validate with: dagdi config validate")
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


@app.command()
def validate() -> None:
    """Validate all YAML configuration files."""
    try:
        # Load all configurations
        configurations = load_all_configurations()
        
        # Merge configurations
        merged = merge_configurations(configurations)
        
        # Validate merged configuration
        config = validate_configuration(merged)
        config = resolve_services(config)
        
        # Display success message
        product_count = len(config.products)
        env_count = sum(len(p.environments) for p in config.products)
        server_count = sum(len(e.servers) for p in config.products for e in p.environments)
        service_count = sum(len(s.services) for p in config.products for e in p.environments for s in e.servers)
        
        typer.echo("✓ Configuration is valid!")
        typer.echo(f"  Products: {product_count}")
        typer.echo(f"  Environments: {env_count}")
        typer.echo(f"  Servers: {server_count}")
        typer.echo(f"  Services: {service_count}")
        
    except ConfigError as e:
        typer.echo(f"Configuration Error: {str(e)}", err=True)
        raise typer.Exit(1)
    except ValidationError as e:
        typer.echo(f"Validation Error: {str(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)


@app.command()
def show_settings() -> None:
    """Show current global settings."""
    try:
        # Load all configurations
        configurations = load_all_configurations()
        
        # Merge configurations
        merged = merge_configurations(configurations)
        
        # Validate merged configuration
        config = validate_configuration(merged)
        config = resolve_services(config)
        
        # Display settings
        settings = config.global_settings
        typer.echo("Global Settings:")
        typer.echo(f"  SSH Timeout: {settings.ssh_timeout} seconds")
        typer.echo(f"  SSH Port: {settings.ssh_port}")
        typer.echo(f"  On Partial Failure: {settings.on_partial_failure}")
        typer.echo(f"  Live Status Table: {settings.live_status_table}")
        typer.echo(f"  Theme: {settings.theme}")
        
    except Exception as e:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
