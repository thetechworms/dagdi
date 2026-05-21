"""Unit tests for CLI entry point."""

import pytest
from typer.testing import CliRunner

from src.dagdi.cli import app


class TestCLIEntry:
    """Tests for CLI entry point."""
    
    def test_cli_help(self):
        """Test CLI help command."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "Dagdi" in result.stdout
        assert "Context-aware" in result.stdout
    
    def test_cli_list_help(self):
        """Test list command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["list", "--help"])
        
        assert result.exit_code == 0
        assert "products" in result.stdout.lower() or "List" in result.stdout
    
    def test_cli_manage_help(self):
        """Test manage command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["manage", "--help"])
        
        assert result.exit_code == 0
    
    def test_cli_logs_help(self):
        """Test logs command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--help"])
        
        assert result.exit_code == 0
    
    def test_cli_context_help(self):
        """Test context command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["context", "--help"])
        
        assert result.exit_code == 0
    
    def test_cli_config_help(self):
        """Test config command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["config", "--help"])
        
        assert result.exit_code == 0
    
    def test_cli_ssh_help(self):
        """Test ssh command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["ssh", "--help"])

        assert result.exit_code == 0

    def test_cli_no_args(self):
        """Test CLI with no arguments shows help."""
        runner = CliRunner()
        result = runner.invoke(app, [])
        
        # Should show help or exit with 0
        assert result.exit_code == 0
    
    def test_cli_global_timeout_flag(self):
        """Test CLI accepts global timeout flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["--timeout", "60", "config", "--help"])
        
        # Should not error on flag parsing
        assert result.exit_code == 0
    
    def test_cli_global_on_failure_flag(self):
        """Test CLI accepts global on-failure flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["--on-failure", "continue", "config", "--help"])
        
        # Should not error on flag parsing
        assert result.exit_code == 0


class TestCLICommandGroups:
    """Tests for CLI command groups."""
    
    def test_list_command_group_exists(self):
        """Test list command group is registered."""
        runner = CliRunner()
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
    
    def test_manage_command_group_exists(self):
        """Test manage command group is registered."""
        runner = CliRunner()
        result = runner.invoke(app, ["manage", "--help"])
        assert result.exit_code == 0
    
    def test_logs_command_group_exists(self):
        """Test logs command group is registered."""
        runner = CliRunner()
        result = runner.invoke(app, ["logs", "--help"])
        assert result.exit_code == 0
    
    def test_context_command_group_exists(self):
        """Test context command group is registered."""
        runner = CliRunner()
        result = runner.invoke(app, ["context", "--help"])
        assert result.exit_code == 0
    
    def test_config_command_group_exists(self):
        """Test config command group is registered."""
        runner = CliRunner()
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
