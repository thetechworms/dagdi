"""Unit tests for configuration validator."""

import pytest
from src.dagdi.config.validator import validate_configuration, ValidationError


class TestValidateConfiguration:
    """Tests for configuration validation."""
    
    def test_validate_valid_configuration(self):
        """Should validate a valid configuration."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {"name": "nginx", "type": "systemd"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        result = validate_configuration(config)
        
        assert result is not None
        assert len(result.products) == 1
        assert result.products[0].name == "app"
    
    def test_validate_missing_products_field(self):
        """Should reject configuration without products field."""
        config = {}
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must contain 'products' field" in str(exc_info.value)
    
    def test_validate_products_not_list(self):
        """Should reject if products is not a list."""
        config = {"products": "not a list"}
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "'products' must be a list" in str(exc_info.value)
    
    def test_validate_empty_products(self):
        """Should reject empty products list."""
        config = {"products": []}
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "'products' list cannot be empty" in str(exc_info.value)
    
    def test_validate_product_missing_name(self):
        """Should reject product without name."""
        config = {
            "products": [
                {
                    "environments": []
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have a 'name' field" in str(exc_info.value)
    
    def test_validate_product_missing_environments(self):
        """Should reject product without environments."""
        config = {
            "products": [
                {"name": "app"}
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have 'environments' field" in str(exc_info.value)
    
    def test_validate_environment_missing_name(self):
        """Should reject environment without name."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {"servers": []}
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have a 'name' field" in str(exc_info.value)
    
    def test_validate_environment_missing_servers(self):
        """Should reject environment without servers."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {"name": "dev"}
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have 'servers' field" in str(exc_info.value)
    
    def test_validate_server_missing_name(self):
        """Should reject server without name."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have a 'name' field" in str(exc_info.value)
    
    def test_validate_server_missing_type(self):
        """Should reject server without type."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "ips": ["10.0.1.10"]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have a 'type' field" in str(exc_info.value)
    
    def test_validate_server_missing_ips(self):
        """Should reject server without ips."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have 'ips' field" in str(exc_info.value)
    
    def test_validate_server_empty_ips(self):
        """Should reject server with empty ips list."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "ips list cannot be empty" in str(exc_info.value)

    def test_validate_server_level_sudo_password_prompt_sets_server_scope(self):
        """Per-server prompt config should cache per server."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "prod",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "ssh": {
                                        "username": "ubuntu",
                                        "sudo": True,
                                        "sudo_password": "prompt",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        result = validate_configuration(config)
        ssh_config = result.products[0].environments[0].servers[0].ssh_config

        assert ssh_config.sudo_password is None
        assert ssh_config.sudo_password_prompt is True
        assert ssh_config.sudo_password_prompt_cache_key == (
            "app:prod:web-1:ubuntu:sudo-password"
        )

    def test_validate_shared_sudo_password_prompt_sets_environment_scope(self):
        """Shared servers.ssh prompt config should reuse one cache key."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "prod",
                            "servers": {
                                "ssh": {
                                    "username": "ubuntu",
                                    "sudo": True,
                                    "sudo_password": "prompt",
                                },
                                "items": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                    },
                                    {
                                        "name": "web-2",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.11"],
                                    },
                                ],
                            },
                        }
                    ],
                }
            ]
        }

        result = validate_configuration(config)
        servers = result.products[0].environments[0].servers

        assert servers[0].ssh_config.sudo_password_prompt is True
        assert servers[1].ssh_config.sudo_password_prompt is True
        assert servers[0].ssh_config.sudo_password_prompt_cache_key == (
            "app:prod:ubuntu:shared-sudo-password"
        )
        assert (
            servers[0].ssh_config.sudo_password_prompt_cache_key
            == servers[1].ssh_config.sudo_password_prompt_cache_key
        )
    
    def test_validate_service_missing_name(self):
        """Should reject service without name."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {"type": "systemd"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have a 'name' field" in str(exc_info.value)
    
    def test_validate_service_missing_type(self):
        """Should reject service without type."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {"name": "nginx"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "must have a 'type' field" in str(exc_info.value)
    
    def test_validate_service_invalid_type(self):
        """Should reject service with invalid type."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {"name": "nginx", "type": "invalid"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)
        
        assert "type must be one of" in str(exc_info.value)
    
    def test_validate_service_valid_types(self):
        """Should accept all valid service types."""
        for service_type in ["systemd", "docker"]:
            config = {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {
                                "name": "dev",
                                "servers": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                        "services": [
                                            {"name": "svc", "type": service_type}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
            
            result = validate_configuration(config)
            assert result is not None

    def test_validate_service_friendly_name(self):
        """Should accept service friendly_name when valid."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {
                                            "name": "nginx",
                                            "friendly_name": "Nginx Web Server",
                                            "type": "systemd",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        result = validate_configuration(config)
        assert result.products[0].environments[0].servers[0].services[0].friendly_name == "Nginx Web Server"

    def test_validate_service_friendly_name_invalid(self):
        """Should reject invalid service friendly_name."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {"name": "nginx", "friendly_name": 123, "type": "systemd"}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)

        assert "friendly_name must be a non-empty string" in str(exc_info.value)

    def test_validate_service_metadata_fields(self):
        """Should accept optional service metadata fields."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {
                                            "name": "api",
                                            "type": "docker",
                                            "api_endpoint": "http://10.0.1.10:8080/health",
                                            "port": 8080,
                                            "log_location": "/var/log/myapp-api",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        result = validate_configuration(config)
        svc = result.products[0].environments[0].servers[0].services[0]
        assert svc.api_endpoint == "http://10.0.1.10:8080/health"
        assert svc.port == 8080
        assert svc.log_location == "/var/log/myapp-api"

    def test_validate_service_port_invalid(self):
        """Should reject invalid service port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "services": [
                                        {"name": "api", "type": "docker", "port": 70000}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)

        assert "port must be between 1 and 65535" in str(exc_info.value)
    
    def test_validate_global_settings_ssh_timeout(self):
        """Should validate global settings ssh_timeout."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"]
                                }
                            ]
                        }
                    ]
                }
            ],
            "global_settings": {
                "ssh_timeout": 60
            }
        }
        
        result = validate_configuration(config)
        
        assert result.global_settings.ssh_timeout == 60
    
    def test_validate_global_settings_on_partial_failure(self):
        """Should validate global settings on_partial_failure."""
        for value in ["continue", "stop", "prompt"]:
            config = {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {
                                "name": "dev",
                                "servers": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"]
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "global_settings": {
                    "on_partial_failure": value
                }
            }
            
            result = validate_configuration(config)
            assert result.global_settings.on_partial_failure == value

    def test_validate_global_settings_live_status_table(self):
        """Should validate global settings live_status_table."""
        for value in [True, False]:
            config = {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {
                                "name": "dev",
                                "servers": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"]
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "global_settings": {
                    "live_status_table": value
                }
            }

            result = validate_configuration(config)
            assert result.global_settings.live_status_table == value

    def test_validate_global_settings_live_status_table_invalid_type(self):
        """Should reject non-boolean global settings live_status_table."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"]
                                }
                            ]
                        }
                    ]
                }
            ],
            "global_settings": {
                "live_status_table": "yes"
            }
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_configuration(config)

        assert "'global_settings.live_status_table' must be a boolean" in str(exc_info.value)
    
    def test_validate_server_ssh_config(self):
        """Should validate server SSH configuration."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "ssh": {
                                        "username": "ubuntu",
                                        "key_path": "~/.ssh/id_rsa",
                                        "timeout": 45
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        result = validate_configuration(config)
        
        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.username == "ubuntu"
        assert server.ssh_config.key_path == "~/.ssh/id_rsa"
        assert server.ssh_config.timeout == 45

    def test_validate_environment_servers_shared_ssh_defaults(self):
        """Should apply shared servers.ssh defaults to each server."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": {
                                "ssh": {
                                    "username": "deploy-user",
                                    "key_path": "~/.ssh/servers",
                                    "timeout": 30,
                                    "sudo": True,
                                },
                                "items": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                    }
                                ],
                            },
                        }
                    ]
                }
            ]
        }

        result = validate_configuration(config)

        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.username == "deploy-user"
        assert server.ssh_config.key_path == "~/.ssh/servers"
        assert server.ssh_config.timeout == 30
        assert server.ssh_config.sudo is True

    def test_validate_environment_servers_shared_ssh_can_be_overridden_per_server(self):
        """Should let a server-level ssh block override shared servers.ssh values."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": {
                                "ssh": {
                                    "username": "deploy-user",
                                    "key_path": "~/.ssh/servers",
                                    "timeout": 30,
                                },
                                "items": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                        "ssh": {
                                            "timeout": 60,
                                            "key_path": "~/.ssh/special",
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            ]
        }

        result = validate_configuration(config)

        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.username == "deploy-user"
        assert server.ssh_config.key_path == "~/.ssh/special"
        assert server.ssh_config.timeout == 60

    def test_validate_global_settings_ssh_port(self):
        """Should validate global settings ssh_port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": 2222},
        }

        result = validate_configuration(config)
        assert result.global_settings.ssh_port == 2222

    def test_validate_global_settings_ssh_port_invalid(self):
        """Should reject non-integer ssh_port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": "abc"},
        }

        with pytest.raises(ValidationError, match="ssh_port.*integer"):
            validate_configuration(config)

    def test_validate_global_settings_ssh_port_out_of_range(self):
        """Should reject ssh_port outside 1-65535."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": 70000},
        }

        with pytest.raises(ValidationError, match="ssh_port.*between 1 and 65535"):
            validate_configuration(config)

    def test_validate_global_ssh_port_applies_to_servers(self):
        """Global ssh_port should be the default for servers without explicit port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": 2222},
        }

        result = validate_configuration(config)
        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.port == 2222

    def test_validate_server_ssh_port_overrides_global(self):
        """Per-server ssh port should override global ssh_port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": [
                                {
                                    "name": "web-1",
                                    "type": "ubuntu",
                                    "ips": ["10.0.1.10"],
                                    "ssh": {"port": 3333},
                                }
                            ],
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": 2222},
        }

        result = validate_configuration(config)
        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.port == 3333

    def test_validate_shared_env_ssh_port_overrides_global(self):
        """Environment-level shared ssh port should override global ssh_port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": {
                                "ssh": {"username": "deploy", "port": 4444},
                                "items": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": 2222},
        }

        result = validate_configuration(config)
        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.port == 4444

    def test_validate_server_port_overrides_env_and_global(self):
        """Per-server port should override both environment-level and global port."""
        config = {
            "products": [
                {
                    "name": "app",
                    "environments": [
                        {
                            "name": "dev",
                            "servers": {
                                "ssh": {"username": "deploy", "port": 4444},
                                "items": [
                                    {
                                        "name": "web-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                        "ssh": {"port": 5555},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
            "global_settings": {"ssh_port": 2222},
        }

        result = validate_configuration(config)
        server = result.products[0].environments[0].servers[0]
        assert server.ssh_config.port == 5555
