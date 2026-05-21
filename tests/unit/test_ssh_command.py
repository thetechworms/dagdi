"""Unit tests for the dagdi ssh command."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.dagdi.cli import app
from src.dagdi.commands.ssh import (
    _build_ssh_args,
    _find_ssh_binary,
    _prompt_ip_selection,
)
from src.dagdi.models import SSHConfig, Server, Service


def _make_server(
    name="web-1",
    ips=None,
    username="ubuntu",
    key_path=None,
    port=22,
    services=None,
):
    """Helper to build a Server with sensible defaults."""
    return Server(
        name=name,
        type="ubuntu",
        ips=ips or ["10.0.1.10"],
        ssh_config=SSHConfig(username=username, key_path=key_path, port=port),
        services=services or [],
    )


class TestFindSshBinary:
    """Tests for _find_ssh_binary."""

    @patch("src.dagdi.commands.ssh.shutil.which", return_value="/usr/bin/ssh")
    def test_finds_ssh(self, mock_which):
        assert _find_ssh_binary() == "/usr/bin/ssh"

    @patch("src.dagdi.commands.ssh.shutil.which", return_value=None)
    def test_raises_when_not_found(self, mock_which):
        with pytest.raises(RuntimeError, match="Could not find 'ssh'"):
            _find_ssh_binary()


class TestBuildSshArgs:
    """Tests for _build_ssh_args."""

    def test_basic_args(self):
        server = _make_server()
        args = _build_ssh_args("/usr/bin/ssh", server, "10.0.1.10")
        assert args[0] == "/usr/bin/ssh"
        assert "ubuntu@10.0.1.10" in args
        assert "-o" in args
        assert "StrictHostKeyChecking=no" in args

    def test_key_path(self):
        server = _make_server(key_path="~/.ssh/id_rsa")
        args = _build_ssh_args("/usr/bin/ssh", server, "10.0.1.10")
        assert "-i" in args
        idx = args.index("-i")
        assert args[idx + 1] == os.path.expanduser("~/.ssh/id_rsa")

    def test_custom_port(self):
        server = _make_server(port=2222)
        args = _build_ssh_args("/usr/bin/ssh", server, "10.0.1.10")
        assert "-p" in args
        idx = args.index("-p")
        assert args[idx + 1] == "2222"

    def test_default_port_omitted(self):
        server = _make_server(port=22)
        args = _build_ssh_args("/usr/bin/ssh", server, "10.0.1.10")
        assert "-p" not in args

    def test_no_key_path(self):
        server = _make_server(key_path=None)
        args = _build_ssh_args("/usr/bin/ssh", server, "10.0.1.10")
        assert "-i" not in args


class TestPromptIpSelection:
    """Tests for _prompt_ip_selection."""

    def test_single_ip_returns_directly(self):
        server = _make_server(ips=["10.0.1.10"])
        assert _prompt_ip_selection(server) == "10.0.1.10"


class TestSshCliHelp:
    """Tests for the ssh command registration and help."""

    def test_ssh_help(self):
        runner = CliRunner()
        result = runner.invoke(app, ["ssh", "--help"])
        assert result.exit_code == 0
        assert "SSH into a server" in result.stdout or "ssh" in result.stdout.lower()

    def test_ssh_shows_product_option(self):
        runner = CliRunner()
        result = runner.invoke(app, ["ssh", "--help"])
        assert "--product" in result.stdout
        assert "--environment" in result.stdout
        assert "--server" in result.stdout
        assert "--ip" in result.stdout


class TestSshCommand:
    """Integration-style tests for the ssh command flow."""

    def _mock_config_pipeline(self, servers):
        """Return a set of patches that make the config pipeline return servers."""
        from src.dagdi.models import (
            Configuration, Product, Environment, GlobalSettings,
        )
        from src.dagdi.resolver import ResolvedScope

        config = Configuration(
            products=[
                Product(
                    name="app",
                    environments=[
                        Environment(name="prod", servers=servers),
                    ],
                )
            ],
            global_settings=GlobalSettings(),
        )

        scope = ResolvedScope(
            product="app",
            environment="prod",
            servers=servers,
        )

        return {
            "load_all_configurations": MagicMock(return_value=[{}]),
            "merge_configurations": MagicMock(return_value={}),
            "validate_configuration": MagicMock(return_value=config),
            "resolve_services": MagicMock(return_value=config),
            "get_context": MagicMock(
                return_value={"product": "app", "environment": "prod"}
            ),
            "resolve_scope": MagicMock(return_value=scope),
        }

    @patch("src.dagdi.commands.ssh.shutil.which", return_value="/usr/bin/ssh")
    def test_single_server_connects_directly(self, mock_which):
        """With one server, skip the picker and exec ssh."""
        server = _make_server()
        mocks = self._mock_config_pipeline([server])

        with (
            patch("src.dagdi.commands.ssh.load_all_configurations", mocks["load_all_configurations"]),
            patch("src.dagdi.commands.ssh.merge_configurations", mocks["merge_configurations"]),
            patch("src.dagdi.commands.ssh.validate_configuration", mocks["validate_configuration"]),
            patch("src.dagdi.commands.ssh.resolve_services", mocks["resolve_services"]),
            patch("src.dagdi.commands.ssh.get_context", mocks["get_context"]),
            patch("src.dagdi.commands.ssh.resolve_scope", mocks["resolve_scope"]),
            patch("src.dagdi.commands.ssh._exec_ssh") as mock_exec,
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["ssh", "-p", "app", "-e", "prod"])

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0][0]
            assert args[0] == "/usr/bin/ssh"
            assert "ubuntu@10.0.1.10" in args

    @patch("src.dagdi.commands.ssh.shutil.which", return_value="/usr/bin/ssh")
    def test_multiple_servers_prompts_selection(self, mock_which):
        """With multiple servers, prompt the user to pick one."""
        servers = [
            _make_server(name="web-1", ips=["10.0.1.10"]),
            _make_server(name="db-1", ips=["10.0.1.20"]),
        ]
        mocks = self._mock_config_pipeline(servers)

        with (
            patch("src.dagdi.commands.ssh.load_all_configurations", mocks["load_all_configurations"]),
            patch("src.dagdi.commands.ssh.merge_configurations", mocks["merge_configurations"]),
            patch("src.dagdi.commands.ssh.validate_configuration", mocks["validate_configuration"]),
            patch("src.dagdi.commands.ssh.resolve_services", mocks["resolve_services"]),
            patch("src.dagdi.commands.ssh.get_context", mocks["get_context"]),
            patch("src.dagdi.commands.ssh.resolve_scope", mocks["resolve_scope"]),
            patch("src.dagdi.commands.ssh._exec_ssh") as mock_exec,
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["ssh", "-p", "app", "-e", "prod"], input="1\n")

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0][0]
            assert "ubuntu@10.0.1.10" in args

    @patch("src.dagdi.commands.ssh.shutil.which", return_value="/usr/bin/ssh")
    def test_no_servers_found(self, mock_which):
        """When scope returns no servers, exit with error."""
        mocks = self._mock_config_pipeline([])

        with (
            patch("src.dagdi.commands.ssh.load_all_configurations", mocks["load_all_configurations"]),
            patch("src.dagdi.commands.ssh.merge_configurations", mocks["merge_configurations"]),
            patch("src.dagdi.commands.ssh.validate_configuration", mocks["validate_configuration"]),
            patch("src.dagdi.commands.ssh.resolve_services", mocks["resolve_services"]),
            patch("src.dagdi.commands.ssh.get_context", mocks["get_context"]),
            patch("src.dagdi.commands.ssh.resolve_scope", mocks["resolve_scope"]),
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["ssh", "-p", "app", "-e", "prod"])
            assert result.exit_code == 1

    @patch("src.dagdi.commands.ssh.shutil.which", return_value=None)
    def test_ssh_binary_not_found(self, mock_which):
        """When ssh binary is not found, exit with error."""
        runner = CliRunner()
        result = runner.invoke(app, ["ssh", "-p", "app", "-e", "prod"])
        assert result.exit_code == 1
        assert "ssh" in result.output.lower()

    @patch("src.dagdi.commands.ssh.shutil.which", return_value="/usr/bin/ssh")
    def test_custom_port_in_args(self, mock_which):
        """Non-default port should appear in ssh args."""
        server = _make_server(port=2222)
        mocks = self._mock_config_pipeline([server])

        with (
            patch("src.dagdi.commands.ssh.load_all_configurations", mocks["load_all_configurations"]),
            patch("src.dagdi.commands.ssh.merge_configurations", mocks["merge_configurations"]),
            patch("src.dagdi.commands.ssh.validate_configuration", mocks["validate_configuration"]),
            patch("src.dagdi.commands.ssh.resolve_services", mocks["resolve_services"]),
            patch("src.dagdi.commands.ssh.get_context", mocks["get_context"]),
            patch("src.dagdi.commands.ssh.resolve_scope", mocks["resolve_scope"]),
            patch("src.dagdi.commands.ssh._exec_ssh") as mock_exec,
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["ssh", "-p", "app", "-e", "prod"])

            args = mock_exec.call_args[0][0]
            assert "-p" in args
            port_idx = args.index("-p")
            assert args[port_idx + 1] == "2222"

    @patch("src.dagdi.commands.ssh.shutil.which", return_value="/usr/bin/ssh")
    def test_server_with_multiple_ips_prompts(self, mock_which):
        """When a server has multiple IPs, prompt for selection."""
        server = _make_server(ips=["10.0.1.10", "10.0.1.11"])
        mocks = self._mock_config_pipeline([server])

        with (
            patch("src.dagdi.commands.ssh.load_all_configurations", mocks["load_all_configurations"]),
            patch("src.dagdi.commands.ssh.merge_configurations", mocks["merge_configurations"]),
            patch("src.dagdi.commands.ssh.validate_configuration", mocks["validate_configuration"]),
            patch("src.dagdi.commands.ssh.resolve_services", mocks["resolve_services"]),
            patch("src.dagdi.commands.ssh.get_context", mocks["get_context"]),
            patch("src.dagdi.commands.ssh.resolve_scope", mocks["resolve_scope"]),
            patch("src.dagdi.commands.ssh._exec_ssh") as mock_exec,
        ):
            runner = CliRunner()
            result = runner.invoke(
                app, ["ssh", "-p", "app", "-e", "prod"], input="2\n"
            )

            args = mock_exec.call_args[0][0]
            assert "ubuntu@10.0.1.11" in args
