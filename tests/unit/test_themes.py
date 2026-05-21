"""Unit tests for the theme system."""

import pytest
from dataclasses import fields

from src.dagdi.output.themes import (
    Theme,
    THEMES,
    AVAILABLE_THEMES,
    get_theme,
    set_theme,
    styled,
)


class TestThemeDataclass:

    def test_default_theme_has_all_fields_populated(self):
        t = THEMES["default"]
        for f in fields(Theme):
            assert getattr(t, f.name) != "", f"default theme field '{f.name}' should not be empty"

    def test_no_color_theme_has_all_fields_empty(self):
        t = THEMES["no_color"]
        for f in fields(Theme):
            assert getattr(t, f.name) == "", f"no_color theme field '{f.name}' should be empty"

    def test_available_themes_matches_keys(self):
        assert set(AVAILABLE_THEMES) == set(THEMES.keys())

    def test_four_preset_themes_exist(self):
        assert "default" in THEMES
        assert "light" in THEMES
        assert "dark" in THEMES
        assert "no_color" in THEMES


class TestSetAndGetTheme:

    def test_default_active_theme(self):
        set_theme("default")
        t = get_theme()
        assert t is THEMES["default"]

    def test_set_theme_changes_active(self):
        set_theme("dark")
        assert get_theme() is THEMES["dark"]
        set_theme("default")

    def test_set_theme_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown theme 'nonexistent'"):
            set_theme("nonexistent")

    def test_set_theme_no_color(self):
        set_theme("no_color")
        assert get_theme() is THEMES["no_color"]
        set_theme("default")


class TestStyled:

    def test_styled_wraps_with_markup(self):
        set_theme("default")
        result = styled("hello", "success")
        t = THEMES["default"]
        assert result == f"[{t.success}]hello[/{t.success}]"

    def test_styled_no_color_returns_plain(self):
        set_theme("no_color")
        result = styled("hello", "success")
        assert result == "hello"
        set_theme("default")

    def test_styled_unknown_role_returns_plain(self):
        set_theme("default")
        result = styled("hello", "nonexistent_role")
        assert result == "hello"

    def test_styled_with_dark_theme(self):
        set_theme("dark")
        result = styled("hello", "error")
        t = THEMES["dark"]
        assert result == f"[{t.error}]hello[/{t.error}]"
        set_theme("default")


class TestThemeIntegrationWithFormatter:

    def test_colorize_metric_uses_theme(self):
        from src.dagdi.output.formatter import colorize_metric

        set_theme("default")
        result = colorize_metric(90.0)
        t = THEMES["default"]
        assert t.metric_critical in result

        result = colorize_metric(60.0)
        assert t.metric_warning in result

        result = colorize_metric(30.0)
        assert t.metric_normal in result

    def test_colorize_metric_no_color(self):
        from src.dagdi.output.formatter import colorize_metric

        set_theme("no_color")
        result = colorize_metric(90.0)
        assert "[" not in result
        assert result == "90.0"
        set_theme("default")

    def test_format_status_indicator_uses_theme(self):
        from src.dagdi.output.formatter import format_status_indicator

        set_theme("default")
        t = THEMES["default"]
        result = format_status_indicator("RUNNING")
        assert t.status_running in result
        assert "RUNNING" in result

    def test_format_status_indicator_no_color(self):
        from src.dagdi.output.formatter import format_status_indicator

        set_theme("no_color")
        result = format_status_indicator("RUNNING")
        assert result == "● RUNNING"
        assert "[" not in result
        set_theme("default")

    def test_highlight_log_line_uses_theme(self):
        from src.dagdi.output.formatter import highlight_log_line

        set_theme("default")
        t = THEMES["default"]
        result = highlight_log_line("2024-01-01 ERROR something broke")
        assert t.log_error in result

        set_theme("no_color")
        result = highlight_log_line("2024-01-01 ERROR something broke")
        assert "[" not in result
        set_theme("default")


class TestThemeValidation:

    def test_validator_accepts_valid_theme(self):
        from src.dagdi.config.validator import validate_configuration

        config_dict = {
            "products": [{
                "name": "app",
                "environments": [{
                    "name": "dev",
                    "servers": [{
                        "name": "web",
                        "type": "ubuntu",
                        "ips": ["10.0.1.1"],
                    }],
                }],
            }],
            "global_settings": {"theme": "dark"},
        }
        config = validate_configuration(config_dict)
        assert config.global_settings.theme == "dark"
        set_theme("default")

    def test_validator_rejects_invalid_theme(self):
        from src.dagdi.config.validator import validate_configuration, ValidationError

        config_dict = {
            "products": [{
                "name": "app",
                "environments": [{
                    "name": "dev",
                    "servers": [{
                        "name": "web",
                        "type": "ubuntu",
                        "ips": ["10.0.1.1"],
                    }],
                }],
            }],
            "global_settings": {"theme": "rainbow"},
        }
        with pytest.raises(ValidationError, match="global_settings.theme"):
            validate_configuration(config_dict)

    def test_validator_default_theme_when_not_specified(self):
        from src.dagdi.config.validator import validate_configuration

        config_dict = {
            "products": [{
                "name": "app",
                "environments": [{
                    "name": "dev",
                    "servers": [{
                        "name": "web",
                        "type": "ubuntu",
                        "ips": ["10.0.1.1"],
                    }],
                }],
            }],
        }
        config = validate_configuration(config_dict)
        assert config.global_settings.theme == "default"
