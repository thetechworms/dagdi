"""Core data models for Dagdi CLI configuration and context."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime


@dataclass
class SSHConfig:
    """SSH connection configuration for a server."""
    
    username: str
    password: Optional[str] = None
    key_path: Optional[str] = None
    port: int = 22
    timeout: int = 30
    sudo: bool = False
    sudo_password: Optional[str] = None
    sudo_password_prompt: bool = False
    sudo_password_prompt_cache_key: Optional[str] = None
    sudo_password_prompt_label: Optional[str] = None
    sudo_nopasswd: Optional[bool] = None


@dataclass
class Service:
    """Service definition within a server."""
    
    name: str
    type: Literal["systemd", "docker"]
    friendly_name: Optional[str] = None
    api_endpoint: Optional[str] = None
    port: Optional[int] = None
    log_location: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Server:
    """Server definition within an environment."""
    
    name: str
    type: str  # OS type (ubuntu, centos, etc.)
    ips: List[str]
    ssh_config: SSHConfig
    services: List[Service] = field(default_factory=list)
    service_names: List[str] = field(default_factory=list)  # References to global services


@dataclass
class Environment:
    """Environment definition within a product."""
    
    name: str
    servers: List[Server] = field(default_factory=list)


@dataclass
class Product:
    """Product definition containing environments."""
    
    name: str
    environments: List[Environment] = field(default_factory=list)


@dataclass
class GlobalSettings:
    """Global settings for Dagdi CLI."""

    ssh_timeout: int = 30
    ssh_port: int = 22
    on_partial_failure: Literal["continue", "stop", "prompt"] = "prompt"
    live_status_table: bool = False
    theme: str = "default"


@dataclass
class Configuration:
    """Complete configuration loaded from YAML files."""
    
    products: List[Product] = field(default_factory=list)
    services: List[Service] = field(default_factory=list)  # Global services registry
    global_settings: GlobalSettings = field(default_factory=GlobalSettings)


@dataclass
class Context:
    """User's current working context (product + environment)."""
    
    product: str
    environment: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResult:
    """Result of SSH command execution."""
    
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.error is None and self.return_code == 0
    
    @property
    def failed(self) -> bool:
        """Check if execution failed."""
        return not self.success
