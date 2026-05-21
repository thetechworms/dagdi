"""Unit tests for configuration merger."""

import pytest
from src.dagdi.config.merger import merge_configurations, MergeError


class TestMergeConfigurations:
    """Tests for YAML configuration merging."""
    
    def test_merge_single_configuration(self):
        """Should handle single configuration."""
        configs = [
            {
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
                                        "services": [{"name": "nginx", "type": "systemd"}]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
        
        merged = merge_configurations(configs)
        
        assert len(merged["products"]) == 1
        assert merged["products"][0]["name"] == "app"
        assert len(merged["products"][0]["environments"]) == 1
    
    def test_merge_multiple_products(self):
        """Should merge multiple products from different files."""
        configs = [
            {
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
                                        "services": []
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "products": [
                    {
                        "name": "db",
                        "environments": [
                            {
                                "name": "dev",
                                "servers": [
                                    {
                                        "name": "db-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.2.10"],
                                        "services": []
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
        
        merged = merge_configurations(configs)
        
        assert len(merged["products"]) == 2
        product_names = {p["name"] for p in merged["products"]}
        assert product_names == {"app", "db"}
    
    def test_duplicate_product_across_files_raises_error(self):
        """Should reject duplicate product names across files."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-app-dev.yaml",
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {
                                "name": "dev",
                                "servers": [
                                    {
                                        "name": "web-dev",
                                        "type": "ubuntu",
                                        "ips": ["10.0.1.10"],
                                        "services": []
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "__dagdi_source_file": "config/dagdi-app-prod.yaml",
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {
                                "name": "prod",
                                "servers": [
                                    {
                                        "name": "web-prod",
                                        "type": "ubuntu",
                                        "ips": ["10.0.2.10"],
                                        "services": []
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        with pytest.raises(MergeError) as exc_info:
            merge_configurations(configs)

        message = str(exc_info.value)
        assert "Duplicate product 'app'" in message
        assert "config/dagdi-app-dev.yaml" in message
        assert "config/dagdi-app-prod.yaml" in message

    def test_merge_same_environment_different_servers_requires_single_file(self):
        """Should reject same product split across files, even for different servers."""
        configs = [
            {
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
                                        "services": []
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {
                                "name": "dev",
                                "servers": [
                                    {
                                        "name": "db-1",
                                        "type": "ubuntu",
                                        "ips": ["10.0.2.10"],
                                        "services": []
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        with pytest.raises(MergeError):
            merge_configurations(configs)

    def test_merge_same_server_different_services_requires_single_file(self):
        """Should reject same product split across files, even for different services."""
        configs = [
            {
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
                                        "services": [{"name": "nginx", "type": "systemd"}]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
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
                                        "services": [{"name": "api", "type": "docker"}]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        with pytest.raises(MergeError):
            merge_configurations(configs)

    def test_merge_duplicate_service_not_duplicated_requires_single_file(self):
        """Should reject duplicate product split across files."""
        configs = [
            {
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
                                        "services": [{"name": "nginx", "type": "systemd"}]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
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
                                        "services": [{"name": "nginx", "type": "systemd"}]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        with pytest.raises(MergeError):
            merge_configurations(configs)
    
    def test_merge_global_settings(self):
        """Should merge global settings."""
        configs = [
            {
                "products": [{"name": "app", "environments": []}],
                "global_settings": {"ssh_timeout": 30}
            },
            {
                "products": [{"name": "db", "environments": []}],
                "global_settings": {"on_partial_failure": "continue"}
            }
        ]
        
        merged = merge_configurations(configs)
        
        assert merged["global_settings"]["ssh_timeout"] == 30
        assert merged["global_settings"]["on_partial_failure"] == "continue"
    
    def test_merge_empty_configurations(self):
        """Should handle empty configurations."""
        configs = [
            {"products": []},
            {"products": []}
        ]
        
        merged = merge_configurations(configs)
        
        assert merged["products"] == []
