"""Unit tests for configuration loader."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.dagdi.config.loader import (
    discover_yaml_files,
    load_yaml_file,
    load_all_configurations,
    get_default_config_dir,
    ConfigError,
)


class TestGetDefaultConfigDir:
    """Tests for default config directory resolution."""

    def test_uses_default_dir_when_exists(self, monkeypatch):
        """Should prioritize ~/.config/dagdi when it exists."""
        with TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir)
            default_dir = home_dir / ".config" / "dagdi"
            default_dir.mkdir(parents=True)
            monkeypatch.setattr(Path, "home", staticmethod(lambda: home_dir))
            monkeypatch.delenv("DAGDI_CONFIG_DIR", raising=False)

            result = get_default_config_dir()

            assert result == default_dir

    def test_uses_default_dir_over_env_var(self, monkeypatch):
        """Should prefer ~/.config/dagdi over DAGDI_CONFIG_DIR when default exists."""
        with TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir)
            default_dir = home_dir / ".config" / "dagdi"
            default_dir.mkdir(parents=True)
            custom_dir = Path(tmpdir) / "custom-config"
            monkeypatch.setattr(Path, "home", staticmethod(lambda: home_dir))
            monkeypatch.setenv("DAGDI_CONFIG_DIR", str(custom_dir))

            result = get_default_config_dir()

            assert result == default_dir

    def test_uses_env_var_when_default_missing(self, monkeypatch):
        """Should fall back to DAGDI_CONFIG_DIR when ~/.config/dagdi doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir) / "empty-home"
            home_dir.mkdir()
            custom_dir = Path(tmpdir) / "my-dagdi-config"
            monkeypatch.setattr(Path, "home", staticmethod(lambda: home_dir))
            monkeypatch.setenv("DAGDI_CONFIG_DIR", str(custom_dir))

            result = get_default_config_dir()

            assert result == custom_dir

    def test_returns_default_dir_when_nothing_exists(self, monkeypatch):
        """Should return ~/.config/dagdi even when nothing exists (for error messages)."""
        with TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir) / "empty-home"
            home_dir.mkdir()
            monkeypatch.setattr(Path, "home", staticmethod(lambda: home_dir))
            monkeypatch.delenv("DAGDI_CONFIG_DIR", raising=False)

            result = get_default_config_dir()

            assert result == home_dir / ".config" / "dagdi"


class TestDiscoverYamlFiles:
    """Tests for YAML file discovery."""
    
    def test_discover_yaml_files_with_yaml_extension(self):
        """Should find files with .yaml extension."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test files
            (config_dir / "dagdi-app.yaml").write_text("products: []")
            (config_dir / "dagdi-db.yaml").write_text("products: []")
            
            files = discover_yaml_files(config_dir)
            
            assert len(files) == 2
            assert any(f.name == "dagdi-app.yaml" for f in files)
            assert any(f.name == "dagdi-db.yaml" for f in files)
    
    def test_discover_yaml_files_with_yml_extension(self):
        """Should find files with .yml extension."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test files
            (config_dir / "dagdi-app.yml").write_text("products: []")
            
            files = discover_yaml_files(config_dir)
            
            assert len(files) == 1
            assert files[0].name == "dagdi-app.yml"
    
    def test_discover_yaml_files_mixed_extensions(self):
        """Should find files with both .yaml and .yml extensions."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test files
            (config_dir / "dagdi-app.yaml").write_text("products: []")
            (config_dir / "dagdi-db.yml").write_text("products: []")
            
            files = discover_yaml_files(config_dir)
            
            assert len(files) == 2
    
    def test_discover_yaml_files_ignores_non_matching_files(self):
        """Should ignore files that don't match the pattern."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test files
            (config_dir / "dagdi-app.yaml").write_text("products: []")
            (config_dir / "config.yaml").write_text("products: []")
            (config_dir / "other.yml").write_text("products: []")
            
            files = discover_yaml_files(config_dir)
            
            assert len(files) == 1
            assert files[0].name == "dagdi-app.yaml"
    
    def test_discover_yaml_files_missing_directory(self):
        """Should raise ConfigError if directory doesn't exist."""
        with pytest.raises(ConfigError) as exc_info:
            discover_yaml_files(Path("nonexistent"))
        
        assert "Config directory not found" in str(exc_info.value)
    
    def test_discover_yaml_files_empty_directory(self):
        """Should raise ConfigError if no YAML files found."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            with pytest.raises(ConfigError) as exc_info:
                discover_yaml_files(config_dir)
            
            assert "No YAML configuration files found" in str(exc_info.value)
    
    def test_discover_yaml_files_sorted(self):
        """Should return files in sorted order."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test files in non-alphabetical order
            (config_dir / "dagdi-z.yaml").write_text("products: []")
            (config_dir / "dagdi-a.yaml").write_text("products: []")
            (config_dir / "dagdi-m.yaml").write_text("products: []")
            
            files = discover_yaml_files(config_dir)
            
            assert [f.name for f in files] == ["dagdi-a.yaml", "dagdi-m.yaml", "dagdi-z.yaml"]


class TestLoadYamlFile:
    """Tests for YAML file loading."""
    
    def test_load_yaml_file_valid(self):
        """Should load valid YAML file."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.yaml"
            file_path.write_text("products:\n  - name: app\n")
            
            content = load_yaml_file(file_path)
            
            assert isinstance(content, dict)
            assert "products" in content
            assert content["products"][0]["name"] == "app"
    
    def test_load_yaml_file_empty(self):
        """Should handle empty YAML file."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.yaml"
            file_path.write_text("")
            
            content = load_yaml_file(file_path)
            
            assert content == {}
    
    def test_load_yaml_file_invalid_syntax(self):
        """Should raise ConfigError for invalid YAML syntax."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.yaml"
            file_path.write_text("invalid: yaml: syntax:")
            
            with pytest.raises(ConfigError) as exc_info:
                load_yaml_file(file_path)
            
            assert "Invalid YAML syntax" in str(exc_info.value)
    
    def test_load_yaml_file_not_found(self):
        """Should raise ConfigError if file doesn't exist."""
        with pytest.raises(ConfigError) as exc_info:
            load_yaml_file(Path("nonexistent.yaml"))
        
        assert "Cannot read configuration file" in str(exc_info.value)


class TestLoadAllConfigurations:
    """Tests for loading all configurations."""
    
    def test_load_all_configurations(self):
        """Should load all YAML files."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test files
            (config_dir / "dagdi-app.yaml").write_text("products:\n  - name: app\n")
            (config_dir / "dagdi-db.yaml").write_text("products:\n  - name: db\n")
            
            configs = load_all_configurations(config_dir)
            
            assert len(configs) == 2
            assert any(c.get("products", [{}])[0].get("name") == "app" for c in configs)
            assert any(c.get("products", [{}])[0].get("name") == "db" for c in configs)
    
    def test_load_all_configurations_single_file(self):
        """Should load single YAML file."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            (config_dir / "dagdi-app.yaml").write_text("products:\n  - name: app\n")
            
            configs = load_all_configurations(config_dir)
            
            assert len(configs) == 1

    def test_load_all_configurations_includes_source_file_metadata(self):
        """Should include source file metadata for downstream merge errors."""
        with TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            file_path = config_dir / "dagdi-app.yaml"
            file_path.write_text("products:\n  - name: app\n")

            configs = load_all_configurations(config_dir)

            assert len(configs) == 1
            assert configs[0]["__dagdi_source_file"].endswith("dagdi-app.yaml")
