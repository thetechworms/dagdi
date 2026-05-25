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
    
    def test_global_settings_embedded_in_product(self):
        """Should embed file's global_settings into its product."""
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

        app = next(p for p in merged["products"] if p["name"] == "app")
        db = next(p for p in merged["products"] if p["name"] == "db")
        assert app["global_settings"]["ssh_timeout"] == 30
        assert app["global_settings"]["on_partial_failure"] == "continue"
        assert "global_settings" not in db

    def test_different_products_different_settings(self):
        """Should allow different products in different files to each have global_settings."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-app.yaml",
                "products": [{"name": "app", "environments": []}],
                "global_settings": {"ssh_timeout": 30}
            },
            {
                "__dagdi_source_file": "config/dagdi-db.yaml",
                "products": [{"name": "db", "environments": []}],
                "global_settings": {"ssh_timeout": 60}
            }
        ]

        merged = merge_configurations(configs)

        app = next(p for p in merged["products"] if p["name"] == "app")
        db = next(p for p in merged["products"] if p["name"] == "db")
        assert app["global_settings"]["ssh_timeout"] == 30
        assert db["global_settings"]["ssh_timeout"] == 60

    def test_split_product_settings_conflict_raises_error(self):
        """Should error when a product split across files has global_settings in both."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-app-dev.yaml",
                "products": [{"name": "app", "environments": [{"name": "dev", "servers": []}]}],
                "global_settings": {"ssh_timeout": 30}
            },
            {
                "__dagdi_source_file": "config/dagdi-app-prod.yaml",
                "products": [{"name": "app", "environments": [{"name": "prod", "servers": []}]}],
                "global_settings": {"ssh_timeout": 60}
            }
        ]

        with pytest.raises(MergeError) as exc_info:
            merge_configurations(configs)

        message = str(exc_info.value)
        assert "global_settings for product 'app'" in message
        assert "multiple files" in message

    def test_split_product_settings_in_one_file_ok(self):
        """Should allow split product with global_settings in only one file."""
        configs = [
            {
                "__dagdi_source_file": "config/dagdi-app-dev.yaml",
                "products": [{"name": "app", "environments": [{"name": "dev", "servers": []}]}],
                "global_settings": {"ssh_timeout": 45}
            },
            {
                "__dagdi_source_file": "config/dagdi-app-prod.yaml",
                "products": [{"name": "app", "environments": [{"name": "prod", "servers": []}]}],
            }
        ]

        merged = merge_configurations(configs)

        app = merged["products"][0]
        assert app["global_settings"]["ssh_timeout"] == 45

    def test_no_global_settings_in_any_file(self):
        """Products without global_settings should not have the key."""
        configs = [
            {"products": [{"name": "app", "environments": []}]},
            {"products": [{"name": "db", "environments": []}]}
        ]

        merged = merge_configurations(configs)

        for product in merged["products"]:
            assert "global_settings" not in product

    def test_merge_empty_configurations(self):
        """Should handle empty configurations."""
        configs = [
            {"products": []},
            {"products": []}
        ]
        
        merged = merge_configurations(configs)
        
        assert merged["products"] == []
