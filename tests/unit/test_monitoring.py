"""Unit tests for monitoring commands."""

import threading
import time
import pytest
from unittest.mock import patch, MagicMock, Mock
from typer.testing import CliRunner

from src.dagdi.commands.monitoring import top, _collect_metrics_for_targets
from src.dagdi.cli import app
from src.dagdi.models import (
    Configuration, Product, Environment, Server, Service, SSHConfig, Context, ExecutionResult
)
from src.dagdi.ssh.metrics_collector import MetricsCollector, Metrics, NETWORK_SAMPLE_SECONDS


def _build_batch_output(
    cpuinfo="", loadavg="", meminfo="", disk="", net1="", net2=""
) -> str:
    """Build the batched command output with section markers."""
    return (
        f"===CPUINFO===\n{cpuinfo}\n"
        f"===LOADAVG===\n{loadavg}\n"
        f"===MEMINFO===\n{meminfo}\n"
        f"===DISK===\n{disk}\n"
        f"===NET1===\n{net1}\n"
        f"===NET2===\n{net2}"
    )


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    ssh_config = SSHConfig(username="ubuntu", key_path="~/.ssh/id_rsa")

    service1 = Service(name="nginx", type="systemd")
    service2 = Service(name="api", type="docker")

    server1 = Server(
        name="web-1",
        type="ubuntu",
        ips=["10.0.1.10", "10.0.1.11"],
        ssh_config=ssh_config,
        services=[service1, service2]
    )

    service3 = Service(name="postgres", type="systemd")
    server2 = Server(
        name="db-1",
        type="ubuntu",
        ips=["10.0.2.10"],
        ssh_config=ssh_config,
        services=[service3]
    )

    env_dev = Environment(name="dev", servers=[server1, server2])
    env_prod = Environment(name="prod", servers=[server1])

    product1 = Product(name="myapp", environments=[env_dev, env_prod])

    return Configuration(products=[product1])


@pytest.fixture
def sample_context():
    """Create a sample context for testing."""
    return Context(product="myapp", environment="dev")


class TestMetricsCollectorParsing:
    """Tests for MetricsCollector static parsing methods."""

    def test_parse_sections(self):
        """Test section parsing from batched output."""
        output = "===FOO===\nline1\nline2\n===BAR===\nline3"
        sections = MetricsCollector._parse_sections(output)
        assert "FOO" in sections
        assert "BAR" in sections
        assert "line1" in sections["FOO"]
        assert "line3" in sections["BAR"]

    def test_parse_cpu_success(self):
        """Test CPU parsing with 4 cores and load 0.5."""
        cpuinfo = "processor\t: 0\nprocessor\t: 1\nprocessor\t: 2\nprocessor\t: 3\n"
        loadavg = "0.5 0.4 0.3 1/100 1234\n"
        assert MetricsCollector._parse_cpu(cpuinfo, loadavg) == 12.5

    def test_parse_cpu_zero_load(self):
        """Test CPU parsing with zero load."""
        cpuinfo = "processor\t: 0\nprocessor\t: 1\n"
        loadavg = "0.0 0.0 0.0 1/100 1234\n"
        assert MetricsCollector._parse_cpu(cpuinfo, loadavg) == 0.0

    def test_parse_cpu_empty_input(self):
        """Test CPU parsing with empty input returns 0."""
        assert MetricsCollector._parse_cpu("", "") == 0.0

    def test_parse_ram_success(self):
        """Test RAM parsing: 25% used."""
        meminfo = "MemTotal:       16384000 kB\nMemAvailable:   12288000 kB\n"
        assert MetricsCollector._parse_ram(meminfo) == 25.0

    def test_parse_ram_full(self):
        """Test RAM parsing when memory is full."""
        meminfo = "MemTotal:       16384000 kB\nMemAvailable:   0 kB\n"
        assert MetricsCollector._parse_ram(meminfo) == 100.0

    def test_parse_disk_success(self):
        """Test disk parsing: 50% used."""
        df = ("Filesystem     1K-blocks    Used Available Use% Mounted on\n"
              "/dev/sda1      10485760 5242880 5242880  50% /\n")
        assert MetricsCollector._parse_disk(df) == 50.0

    def test_parse_disk_empty(self):
        """Test disk parsing: 0% used."""
        df = ("Filesystem     1K-blocks    Used Available Use% Mounted on\n"
              "/dev/sda1      10485760 0 10485760  0% /\n")
        assert MetricsCollector._parse_disk(df) == 0.0

    def test_parse_network_success(self):
        """Test network parsing with traffic delta."""
        net1 = (
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
            "    lo: 1048576  10000    0    0    0     0          0         0  1048576  10000    0    0    0     0       0          0\n"
            "  eth0: 2097152  20000    0    0    0     0          0         0  3145728  30000    0    0    0     0       0          0\n"
        )
        net2 = (
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
            "    lo: 1048576  10000    0    0    0     0          0         0  1048576  10000    0    0    0     0       0          0\n"
            "  eth0: 2411724  20500    0    0    0     0          0         0  3774873  31000    0    0    0     0       0          0\n"
        )
        upload, download = MetricsCollector._parse_network(net1, net2)
        assert upload > 0
        assert download > 0

    def test_parse_network_zero(self):
        """Test network parsing with zero traffic."""
        net = (
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
            "  eth0: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
        )
        upload, download = MetricsCollector._parse_network(net, net)
        assert upload == 0.0
        assert download == 0.0


class TestMetricsCollectorIntegration:
    """Tests for collect_metrics (batched SSH command)."""

    def test_collect_metrics_complete(self):
        """Test complete batched metrics collection via single SSH call."""
        collector = MetricsCollector()

        batch_stdout = _build_batch_output(
            cpuinfo="processor\t: 0\nprocessor\t: 1\n",
            loadavg="0.5 0.4 0.3 1/100 1234\n",
            meminfo="MemTotal:       16384000 kB\nMemAvailable:   12288000 kB\n",
            disk="Filesystem     1K-blocks    Used Available Use% Mounted on\n"
                 "/dev/sda1      10485760 5242880 5242880  50% /\n",
            net1=(
                "Inter-|   Receive                                                |  Transmit\n"
                " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
                "    lo: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
                "  eth0: 2097152  20000    0    0    0     0          0         0  3145728  30000    0    0    0     0       0          0\n"
            ),
            net2=(
                "Inter-|   Receive                                                |  Transmit\n"
                " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
                "    lo: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
                "  eth0: 2411724  20020    0    0    0     0          0         0  3460400  30020    0    0    0     0       0          0\n"
            ),
        )

        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            mock_exec.return_value = ExecutionResult(stdout=batch_stdout, return_code=0)

            server = MagicMock()
            metrics = collector.collect_metrics(server, "10.0.1.10")

            assert metrics.cpu_percent == 25.0
            assert metrics.ram_percent == 25.0
            assert metrics.disk_percent == 50.0
            assert metrics.network_up_mbps >= 0
            assert metrics.network_down_mbps >= 0
            mock_exec.assert_called_once()

    def test_collect_metrics_command_failure(self):
        """Test metrics collection when command returns non-zero."""
        collector = MetricsCollector()

        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            mock_exec.return_value = ExecutionResult(return_code=1)
            server = MagicMock()
            metrics = collector.collect_metrics(server, "10.0.1.10")

            assert metrics.cpu_percent == 0.0
            assert metrics.ram_percent == 0.0

    def test_collect_metrics_transport_error(self):
        """Test metrics collection raises on transport error."""
        collector = MetricsCollector()

        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            mock_exec.return_value = ExecutionResult(error="SSH connection refused")
            server = MagicMock()

            with pytest.raises(RuntimeError, match="Metrics collection failed"):
                collector.collect_metrics(server, "10.0.1.10")


class TestTopCommand:
    """Tests for top command."""

    def test_top_command_imports(self):
        """Test that top command can be imported."""
        from src.dagdi.commands.monitoring import monitoring_app, top
        assert monitoring_app is not None
        assert top is not None

    def test_top_help_includes_monitor_flag(self):
        """Test top help exposes the monitor flag."""
        runner = CliRunner()

        result = runner.invoke(app, ["top", "--help"])

        assert result.exit_code == 0
        assert "--monitor" in result.stdout

    def test_top_monitor_refreshes_until_interrupted(self, sample_config):
        """Test top monitor mode updates live output and exits cleanly on Ctrl+C."""
        runner = CliRunner()
        fake_scope = Mock()
        fake_scope.servers = sample_config.products[0].environments[0].servers[:1]

        class FakeLive:
            def __init__(self, *args, **kwargs):
                self.updated = False
                self.started = False
                self.stopped = False

            def start(self):
                self.started = True

            def update(self, _renderable):
                self.updated = True

            def stop(self):
                self.stopped = True

        fake_live = FakeLive()

        with patch("src.dagdi.commands.monitoring.load_all_configurations", return_value=["cfg"]), \
             patch("src.dagdi.commands.monitoring.merge_configurations", return_value={"merged": True}), \
             patch("src.dagdi.commands.monitoring.validate_configuration", return_value=sample_config), \
             patch("src.dagdi.commands.monitoring.resolve_services", return_value=sample_config), \
             patch("src.dagdi.commands.monitoring.get_context", return_value=None), \
             patch("src.dagdi.commands.monitoring.resolve_scope", return_value=fake_scope), \
             patch("dagdi.ssh.metrics_collector.MetricsCollector.collect_metrics", return_value=Metrics(12.5, 25.0, 50.0, 1.0, 2.0)), \
             patch("src.dagdi.commands.monitoring.Live", return_value=fake_live), \
             patch("src.dagdi.commands.monitoring.time.sleep", side_effect=KeyboardInterrupt):
            result = runner.invoke(app, ["top", "--monitor"])

        assert result.exit_code == 0
        assert "Monitoring stopped." in result.stdout
        assert fake_live.started is True
        assert fake_live.updated is True
        assert fake_live.stopped is True

    def test_collect_metrics_for_targets_runs_targets_in_parallel(self, sample_config):
        """Should collect metrics across targets concurrently while preserving order."""
        target_servers = sample_config.products[0].environments[0].servers
        active_calls = 0
        max_active_calls = 0
        lock = threading.Lock()

        def fake_collect(server, ip, timeout=None):
            nonlocal active_calls, max_active_calls
            assert timeout == 15
            with lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.05)
            with lock:
                active_calls -= 1
            return Metrics(12.5, 25.0, 50.0, 1.0, 2.0)

        with patch("dagdi.ssh.metrics_collector.MetricsCollector.collect_metrics", side_effect=fake_collect):
            results, failures = _collect_metrics_for_targets(target_servers, timeout=15)

        assert failures == []
        assert len(results) == 3
        assert [(row["server"], row["ip"]) for row in results] == [
            ("web-1", "10.0.1.10"),
            ("web-1", "10.0.1.11"),
            ("db-1", "10.0.2.10"),
        ]
        assert max_active_calls > 1
