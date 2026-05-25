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
    
    def test_merge_same_product_different_environments_across_files(self):
        """Should merge environments from multiple files into the same product."""
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

        merged = merge_configurations(configs)

        assert len(merged["products"]) == 1
        product = merged["products"][0]
        assert product["name"] == "app"
        assert len(product["environments"]) == 2
        env_names = {e["name"] for e in product["environments"]}
        assert env_names == {"dev", "prod"}

    def test_merge_same_product_many_files(self):
        """Should merge environments from three or more files into one product."""
        configs = [
            {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {"name": "dev", "servers": []}
                        ]
                    }
                ]
            },
            {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {"name": "staging", "servers": []}
                        ]
                    }
                ]
            },
            {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {"name": "prod", "servers": []}
                        ]
                    }
                ]
            }
        ]

        merged = merge_configurations(configs)

        assert len(merged["products"]) == 1
        env_names = {e["name"] for e in merged["products"][0]["environments"]}
        assert env_names == {"dev", "staging", "prod"}

    def test_merge_multiple_envs_per_file_across_files(self):
        """Should merge when each file contributes multiple environments."""
        configs = [
            {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {"name": "dev", "servers": []},
                            {"name": "staging", "servers": []}
                        ]
                    }
                ]
            },
            {
                "products": [
                    {
                        "name": "app",
                        "environments": [
                            {"name": "prod-east", "servers": []},
                            {"name": "prod-west", "servers": []}
                        ]
                    }
                ]
            }
        ]

        merged = merge_configurations(configs)

        assert len(merged["products"]) == 1
        env_names = {e["name"] for e in merged["products"][0]["environments"]}
        assert env_names == {"dev", "staging", "prod-east", "prod-west"}

    def test_duplicate_environment_across_files_raises_error(self):
        """Should reject duplicate environment names for the same product."""
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
                "__dagdi_source_file": "config/dagdi-app-dev2.yaml",
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

        with pytest.raises(MergeError) as exc_info:
            merge_configurations(configs)

        message = str(exc_info.value)
        assert "Duplicate environment 'dev'" in message
        assert "product 'app'" in message
        assert "config/dagdi-app-dev.yaml" in message
        assert "config/dagdi-app-dev2.yaml" in message
    
    def test_global_settings_from_single_file(self):
        """Should accept global_settings when defined in exactly one file."""
        configs = [
            {
                "products": [{"name": "app", "environments": []}],
                "global_settings": {"ssh_timeout": 30, "on_partial_failure": "continue"}
            },
            {
                "products": [{"name": "db", "environments": []}]
            }
        ]

        merged = merge_configurations(configs)

        assert merged["global_settings"]["ssh_timeout"] == 30
        assert merged["global_settings"]["on_partial_failure"] == "continue"

    def test_global_settings_multiple_files_no_standalone_raises_error(self):
        """Should error when multiple non-dedicated files define global_settings."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-app-dev.yaml",
                "products": [{"name": "app", "environments": []}],
                "global_settings": {"ssh_timeout": 30}
            },
            {
                "__dagdi_source_file": "config/dagdi-app-prod.yaml",
                "products": [{"name": "db", "environments": []}],
                "global_settings": {"on_partial_failure": "continue"}
            }
        ]

        with pytest.raises(MergeError) as exc_info:
            merge_configurations(configs)

        message = str(exc_info.value)
        assert "global_settings found in multiple files" in message
        assert "dedicated file" in message

    def test_global_settings_standalone_file_takes_precedence(self, capsys):
        """Should use dedicated settings file and warn when others also define it."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-app-globalSettings.yaml",
                "products": [],
                "global_settings": {"ssh_timeout": 60, "theme": "dark"}
            },
            {
                "__dagdi_source_file": "config/dagdi-app-dev.yaml",
                "products": [{"name": "app", "environments": []}],
                "global_settings": {"ssh_timeout": 10}
            }
        ]

        merged = merge_configurations(configs)

        assert merged["global_settings"]["ssh_timeout"] == 60
        assert merged["global_settings"]["theme"] == "dark"
        captured = capsys.readouterr()
        assert "dagdi-app-globalSettings.yaml" in captured.err
        assert "dagdi-app-dev.yaml" in captured.err

    def test_global_settings_multiple_standalone_files_raises_error(self):
        """Should error when multiple dedicated settings files exist."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-globalSettings.yaml",
                "products": [],
                "global_settings": {"ssh_timeout": 30}
            },
            {
                "__dagdi_source_file": "config/dagdi-app-globalSettings.yaml",
                "products": [],
                "global_settings": {"ssh_timeout": 60}
            }
        ]

        with pytest.raises(MergeError) as exc_info:
            merge_configurations(configs)

        message = str(exc_info.value)
        assert "multiple dedicated settings files" in message

    def test_no_global_settings_in_any_file(self):
        """Should produce empty global_settings when no file defines it."""
        configs = [
            {"products": [{"name": "app", "environments": []}]},
            {"products": [{"name": "db", "environments": []}]}
        ]

        merged = merge_configurations(configs)

        assert merged["global_settings"] == {}

    def test_merge_empty_configurations(self):
        """Should handle empty configurations."""
        configs = [
            {"products": []},
            {"products": []}
        ]
        
        merged = merge_configurations(configs)
        
        assert merged["products"] == []
