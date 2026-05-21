"""Unit tests for the interactive selection module."""

import pytest
from unittest.mock import patch, MagicMock
from src.dagdi.interactive import (
    select_service,
    select_services,
    select_action,
    _deduplicate_services,
    _service_display,
    _numbered_select_service,
    _numbered_select_services,
    _numbered_select_action,
    VALID_ACTIONS,
)
from src.dagdi.models import Service


@pytest.fixture
def sample_services():
    return [
        Service(name="nginx", type="systemd", friendly_name="Web Server"),
        Service(name="api", type="docker", friendly_name="API Gateway"),
        Service(name="postgres", type="systemd"),
        Service(name="redis", type="docker", friendly_name="Cache"),
    ]


class TestServiceDisplay:
    def test_with_friendly_name(self):
        svc = Service(name="nginx", type="systemd", friendly_name="Web Server")
        assert _service_display(svc) == "Web Server (nginx)"

    def test_without_friendly_name(self):
        svc = Service(name="postgres", type="systemd")
        assert _service_display(svc) == "postgres"


class TestDeduplicateServices:
    def test_removes_duplicates(self):
        svc1 = Service(name="nginx", type="systemd")
        svc2 = Service(name="nginx", type="systemd")
        svc3 = Service(name="api", type="docker")
        result = _deduplicate_services([svc1, svc2, svc3])
        assert len(result) == 2
        assert result[0].name == "nginx"
        assert result[1].name == "api"

    def test_preserves_order(self):
        svc1 = Service(name="redis", type="docker")
        svc2 = Service(name="api", type="docker")
        svc3 = Service(name="nginx", type="systemd")
        result = _deduplicate_services([svc1, svc2, svc3])
        assert [s.name for s in result] == ["redis", "api", "nginx"]

    def test_empty_list(self):
        assert _deduplicate_services([]) == []


class TestNumberedSelectService:
    def test_valid_selection(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "2"
            result = _numbered_select_service(sample_services)
            assert result.name == "api"

    def test_first_selection(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "1"
            result = _numbered_select_service(sample_services)
            assert result.name == "nginx"

    def test_last_selection(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "4"
            result = _numbered_select_service(sample_services)
            assert result.name == "redis"

    def test_invalid_then_valid(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = ["0", "5", "abc", "3"]
            result = _numbered_select_service(sample_services)
            assert result.name == "postgres"

    def test_keyboard_interrupt_returns_none(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = KeyboardInterrupt
            result = _numbered_select_service(sample_services)
            assert result is None

    def test_eof_returns_none(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = EOFError
            result = _numbered_select_service(sample_services)
            assert result is None


class TestNumberedSelectServices:
    def test_single_selection(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "2"
            result = _numbered_select_services(sample_services)
            assert len(result) == 1
            assert result[0].name == "api"

    def test_multiple_selection(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "1,3"
            result = _numbered_select_services(sample_services)
            assert len(result) == 2
            assert result[0].name == "nginx"
            assert result[1].name == "postgres"

    def test_all_selection(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "all"
            result = _numbered_select_services(sample_services)
            assert len(result) == 4

    def test_invalid_then_valid(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = ["0,5", "abc", "1,4"]
            result = _numbered_select_services(sample_services)
            assert len(result) == 2
            assert result[0].name == "nginx"
            assert result[1].name == "redis"

    def test_keyboard_interrupt_returns_empty(self, sample_services):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = KeyboardInterrupt
            result = _numbered_select_services(sample_services)
            assert result == []


class TestNumberedSelectAction:
    def test_valid_selection(self):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "1"
            result = _numbered_select_action()
            assert result == "status"

    def test_restart_selection(self):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.return_value = "4"
            result = _numbered_select_action()
            assert result == "restart"

    def test_invalid_then_valid(self):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = ["0", "abc", "2"]
            result = _numbered_select_action()
            assert result == "start"

    def test_keyboard_interrupt_returns_none(self):
        with patch("src.dagdi.interactive.Console") as MockConsole:
            instance = MockConsole.return_value
            instance.input.side_effect = KeyboardInterrupt
            result = _numbered_select_action()
            assert result is None


class TestSelectServicePublicAPI:
    def test_returns_none_for_empty_list(self):
        assert select_service([]) is None

    def test_auto_selects_single_service(self):
        svc = Service(name="nginx", type="systemd")
        assert select_service([svc]) == svc

    def test_deduplicates_before_selection(self):
        svc1 = Service(name="nginx", type="systemd")
        svc2 = Service(name="nginx", type="systemd")
        result = select_service([svc1, svc2])
        assert result == svc1

    def test_falls_back_to_numbered_when_no_inquirer(self, sample_services):
        with patch("src.dagdi.interactive._has_inquirer", return_value=False), \
             patch("src.dagdi.interactive._numbered_select_service") as mock_numbered:
            mock_numbered.return_value = sample_services[0]
            result = select_service(sample_services)
            mock_numbered.assert_called_once()
            assert result == sample_services[0]

    def test_uses_fuzzy_when_inquirer_available(self, sample_services):
        with patch("src.dagdi.interactive._has_inquirer", return_value=True), \
             patch("src.dagdi.interactive._fuzzy_select_service") as mock_fuzzy:
            mock_fuzzy.return_value = sample_services[1]
            result = select_service(sample_services)
            mock_fuzzy.assert_called_once()
            assert result == sample_services[1]


class TestSelectServicesPublicAPI:
    def test_returns_empty_for_empty_list(self):
        assert select_services([]) == []

    def test_falls_back_to_numbered_when_no_inquirer(self, sample_services):
        with patch("src.dagdi.interactive._has_inquirer", return_value=False), \
             patch("src.dagdi.interactive._numbered_select_services") as mock_numbered:
            mock_numbered.return_value = sample_services[:2]
            result = select_services(sample_services)
            mock_numbered.assert_called_once()
            assert len(result) == 2

    def test_uses_fuzzy_when_inquirer_available(self, sample_services):
        with patch("src.dagdi.interactive._has_inquirer", return_value=True), \
             patch("src.dagdi.interactive._fuzzy_select_services") as mock_fuzzy:
            mock_fuzzy.return_value = sample_services[:3]
            result = select_services(sample_services)
            mock_fuzzy.assert_called_once()
            assert len(result) == 3


class TestSelectActionPublicAPI:
    def test_falls_back_to_numbered_when_no_inquirer(self):
        with patch("src.dagdi.interactive._has_inquirer", return_value=False), \
             patch("src.dagdi.interactive._numbered_select_action") as mock_numbered:
            mock_numbered.return_value = "status"
            result = select_action()
            mock_numbered.assert_called_once()
            assert result == "status"

    def test_uses_fuzzy_when_inquirer_available(self):
        with patch("src.dagdi.interactive._has_inquirer", return_value=True), \
             patch("src.dagdi.interactive._fuzzy_select_action") as mock_fuzzy:
            mock_fuzzy.return_value = "restart"
            result = select_action()
            mock_fuzzy.assert_called_once()
            assert result == "restart"


class TestInteractiveServiceCommands:
    """Tests that service commands trigger interactive mode when args are omitted."""

    @pytest.fixture
    def sample_config(self):
        from src.dagdi.models import (
            Configuration, Product, Environment, Server, SSHConfig,
        )
        ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")
        service1 = Service(name="nginx", type="systemd", friendly_name="Web Server")
        service2 = Service(name="api", type="docker")
        server1 = Server(
            name="web-1", type="ubuntu", ips=["10.0.1.10"],
            ssh_config=ssh_config, services=[service1, service2],
        )
        env = Environment(name="dev", servers=[server1])
        product = Product(name="myapp", environments=[env])
        return Configuration(products=[product])

    def test_ms_interactive_selects_service_and_action(self, sample_config):
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value={"product": "myapp", "environment": "dev"}), \
             patch("src.dagdi.commands.service_management.select_service") as mock_sel_svc, \
             patch("src.dagdi.commands.service_management.select_action") as mock_sel_act, \
             patch("dagdi.ssh.executor.warm_up_connection"), \
             patch("dagdi.ssh.executor.prepare_sudo_auth"), \
             patch("dagdi.ssh.executor.validate_sudo_auth"), \
             patch("dagdi.ssh.executor.execute_command", return_value=MagicMock(
                 stdout="active (running)", return_code=0, error=None, success=True,
             )):
            mock_sel_svc.return_value = Service(name="nginx", type="systemd")
            mock_sel_act.return_value = "status"
            result = runner.invoke(service_app, ["ms"])

        assert result.exit_code == 0
        mock_sel_svc.assert_called_once()
        mock_sel_act.assert_called_once()

    def test_ms_exits_when_user_cancels_service_selection(self, sample_config):
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value={"product": "myapp", "environment": "dev"}), \
             patch("src.dagdi.commands.service_management.select_service", return_value=None):
            result = runner.invoke(service_app, ["ms"])

        assert result.exit_code == 0

    def test_ms_skips_interactive_when_args_provided(self, sample_config):
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value=None), \
             patch("src.dagdi.commands.service_management.select_service") as mock_sel_svc, \
             patch("src.dagdi.commands.service_management.select_action") as mock_sel_act, \
             patch("dagdi.ssh.executor.warm_up_connection"), \
             patch("dagdi.ssh.executor.prepare_sudo_auth"), \
             patch("dagdi.ssh.executor.validate_sudo_auth"), \
             patch("dagdi.ssh.executor.execute_command", return_value=MagicMock(
                 stdout="active (running)", return_code=0, error=None, success=True,
             )):
            result = runner.invoke(service_app, ["ms", "nginx", "status", "-p", "myapp", "-e", "dev"])

        mock_sel_svc.assert_not_called()
        mock_sel_act.assert_not_called()

    def test_mss_interactive_selects_services_and_action(self, sample_config):
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value={"product": "myapp", "environment": "dev"}), \
             patch("src.dagdi.commands.service_management.select_services") as mock_sel_svcs, \
             patch("src.dagdi.commands.service_management.select_action") as mock_sel_act, \
             patch("dagdi.ssh.executor.warm_up_connection"), \
             patch("dagdi.ssh.executor.prepare_sudo_auth"), \
             patch("dagdi.ssh.executor.validate_sudo_auth"), \
             patch("dagdi.ssh.executor.execute_command", return_value=MagicMock(
                 stdout="active (running)", return_code=0, error=None, success=True,
             )):
            mock_sel_svcs.return_value = [
                Service(name="nginx", type="systemd"),
                Service(name="api", type="docker"),
            ]
            mock_sel_act.return_value = "status"
            result = runner.invoke(service_app, ["mss"])

        assert result.exit_code == 0
        mock_sel_svcs.assert_called_once()
        mock_sel_act.assert_called_once()

    def test_mas_interactive_selects_action(self, sample_config):
        from typer.testing import CliRunner
        from src.dagdi.commands.service_management import service_app

        runner = CliRunner()

        with patch("src.dagdi.commands.service_management.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.service_management.merge_configurations", return_value={}), \
             patch("src.dagdi.commands.service_management.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.service_management.get_context", return_value={"product": "myapp", "environment": "dev"}), \
             patch("src.dagdi.commands.service_management.select_action") as mock_sel_act, \
             patch("dagdi.ssh.executor.warm_up_connection"), \
             patch("dagdi.ssh.executor.prepare_sudo_auth"), \
             patch("dagdi.ssh.executor.validate_sudo_auth"), \
             patch("dagdi.ssh.executor.execute_command", return_value=MagicMock(
                 stdout="active (running)", return_code=0, error=None, success=True,
             )):
            mock_sel_act.return_value = "status"
            result = runner.invoke(service_app, ["mas"])

        assert result.exit_code == 0
        mock_sel_act.assert_called_once()
