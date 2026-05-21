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
from src.dagdi.ssh.metrics_collector import MetricsCollector, Metrics


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


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_collect_cpu_metrics_success(self):
        """Test successful CPU metrics collection."""
        collector = MetricsCollector()
        
        # Mock the execute_command function
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            # Mock cpuinfo response
            cpuinfo_result = ExecutionResult(
                stdout="processor\t: 0\nprocessor\t: 1\nprocessor\t: 2\nprocessor\t: 3\n",
                return_code=0
            )
            # Mock loadavg response
            loadavg_result = ExecutionResult(
                stdout="0.5 0.4 0.3 1/100 1234\n",
                return_code=0
            )
            
            mock_exec.side_effect = [cpuinfo_result, loadavg_result]
            
            server = MagicMock()
            cpu_percent = collector._collect_cpu_metrics(server, "10.0.1.10")
            
            # With 4 CPUs and load avg of 0.5, CPU% should be (0.5/4)*100 = 12.5%
            assert cpu_percent == 12.5

    def test_collect_cpu_metrics_zero_load(self):
        """Test CPU metrics collection with zero load."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            cpuinfo_result = ExecutionResult(
                stdout="processor\t: 0\nprocessor\t: 1\n",
                return_code=0
            )
            loadavg_result = ExecutionResult(
                stdout="0.0 0.0 0.0 1/100 1234\n",
                return_code=0
            )
            
            mock_exec.side_effect = [cpuinfo_result, loadavg_result]
            
            server = MagicMock()
            cpu_percent = collector._collect_cpu_metrics(server, "10.0.1.10")
            
            assert cpu_percent == 0.0

    def test_collect_cpu_metrics_command_failure(self):
        """Test CPU metrics collection when command fails."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            mock_exec.return_value = ExecutionResult(return_code=1)
            
            server = MagicMock()
            cpu_percent = collector._collect_cpu_metrics(server, "10.0.1.10")
            
            assert cpu_percent == 0.0

    def test_collect_ram_metrics_success(self):
        """Test successful RAM metrics collection."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            meminfo_result = ExecutionResult(
                stdout="MemTotal:       16384000 kB\nMemAvailable:   12288000 kB\n",
                return_code=0
            )
            mock_exec.return_value = meminfo_result
            
            server = MagicMock()
            ram_percent = collector._collect_ram_metrics(server, "10.0.1.10")
            
            # Used = 16384000 - 12288000 = 4096000
            # Percentage = (4096000 / 16384000) * 100 = 25%
            assert ram_percent == 25.0

    def test_collect_ram_metrics_full(self):
        """Test RAM metrics collection when memory is full."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            meminfo_result = ExecutionResult(
                stdout="MemTotal:       16384000 kB\nMemAvailable:   0 kB\n",
                return_code=0
            )
            mock_exec.return_value = meminfo_result
            
            server = MagicMock()
            ram_percent = collector._collect_ram_metrics(server, "10.0.1.10")
            
            assert ram_percent == 100.0

    def test_collect_disk_metrics_success(self):
        """Test successful disk metrics collection."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            df_result = ExecutionResult(
                stdout="Filesystem     1K-blocks    Used Available Use% Mounted on\n/dev/sda1      10485760 5242880 5242880  50% /\n",
                return_code=0
            )
            mock_exec.return_value = df_result
            
            server = MagicMock()
            disk_percent = collector._collect_disk_metrics(server, "10.0.1.10")
            
            assert disk_percent == 50.0

    def test_collect_disk_metrics_empty(self):
        """Test disk metrics collection when disk is empty."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec:
            df_result = ExecutionResult(
                stdout="Filesystem     1K-blocks    Used Available Use% Mounted on\n/dev/sda1      10485760 0 10485760  0% /\n",
                return_code=0
            )
            mock_exec.return_value = df_result
            
            server = MagicMock()
            disk_percent = collector._collect_disk_metrics(server, "10.0.1.10")
            
            assert disk_percent == 0.0

    def test_collect_network_metrics_success(self):
        """Test successful network metrics collection."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec, \
             patch('src.dagdi.ssh.metrics_collector.time.sleep') as mock_sleep, \
             patch('src.dagdi.ssh.metrics_collector.time.monotonic') as mock_monotonic:
            net_dev_result_1 = ExecutionResult(
                stdout="Inter-|   Receive                                                |  Transmit\n"
                       " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
                       "    lo: 1048576  10000    0    0    0     0          0         0  1048576  10000    0    0    0     0       0          0\n"
                       "  eth0: 2097152  20000    0    0    0     0          0         0  3145728  30000    0    0    0     0       0          0\n",
                return_code=0
            )
            net_dev_result_2 = ExecutionResult(
                stdout="Inter-|   Receive                                                |  Transmit\n"
                       " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
                       "    lo: 1048576  10000    0    0    0     0          0         0  1048576  10000    0    0    0     0       0          0\n"
                       "  eth0: 3145728  21000    0    0    0     0          0         0  5242880  32000    0    0    0     0       0          0\n",
                return_code=0
            )
            mock_exec.side_effect = [net_dev_result_1, net_dev_result_2]
            mock_monotonic.side_effect = [100.0, 101.0]
            
            server = MagicMock()
            upload_mbps, download_mbps = collector._collect_network_metrics(server, "10.0.1.10")
            
            # Delta over 1 second: recv=1MB/s, sent=2MB/s
            assert download_mbps == 1.0
            assert upload_mbps == 2.0
            mock_sleep.assert_called_once_with(collector.NETWORK_SAMPLE_SECONDS)

    def test_collect_network_metrics_zero(self):
        """Test network metrics collection with zero traffic."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec, \
             patch('src.dagdi.ssh.metrics_collector.time.sleep') as mock_sleep, \
             patch('src.dagdi.ssh.metrics_collector.time.monotonic') as mock_monotonic:
            net_dev_result_1 = ExecutionResult(
                stdout="Inter-|   Receive                                                |  Transmit\n"
                       " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
                       "    lo: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
                       "  eth0: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n",
                return_code=0
            )
            net_dev_result_2 = ExecutionResult(
                stdout="Inter-|   Receive                                                |  Transmit\n"
                       " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
                       "    lo: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
                       "  eth0: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n",
                return_code=0
            )
            mock_exec.side_effect = [net_dev_result_1, net_dev_result_2]
            mock_monotonic.side_effect = [200.0, 201.0]
            
            server = MagicMock()
            upload_mbps, download_mbps = collector._collect_network_metrics(server, "10.0.1.10")
            
            assert download_mbps == 0.0
            assert upload_mbps == 0.0
            mock_sleep.assert_called_once_with(collector.NETWORK_SAMPLE_SECONDS)

    def test_collect_metrics_complete(self):
        """Test complete metrics collection."""
        collector = MetricsCollector()
        
        with patch('src.dagdi.ssh.metrics_collector.execute_command') as mock_exec, \
             patch('src.dagdi.ssh.metrics_collector.time.sleep') as mock_sleep, \
             patch('src.dagdi.ssh.metrics_collector.time.monotonic') as mock_monotonic:
            # Mock all command responses
            cpuinfo_result = ExecutionResult(
                stdout="processor\t: 0\nprocessor\t: 1\n",
                return_code=0
            )
            loadavg_result = ExecutionResult(
                stdout="0.5 0.4 0.3 1/100 1234\n",
                return_code=0
            )
            meminfo_result = ExecutionResult(
                stdout="MemTotal:       16384000 kB\nMemAvailable:   12288000 kB\n",
                return_code=0
            )
            df_result = ExecutionResult(
                stdout="Filesystem     1K-blocks    Used Available Use% Mounted on\n/dev/sda1      10485760 5242880 5242880  50% /\n",
                return_code=0
            )
            net_dev_result_1 = ExecutionResult(
                stdout="Inter-|   Receive                                                |  Transmit\n"
                       " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
                       "    lo: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
                       "  eth0: 2097152  20000    0    0    0     0          0         0  3145728  30000    0    0    0     0       0          0\n",
                return_code=0
            )
            net_dev_result_2 = ExecutionResult(
                stdout="Inter-|   Receive                                                |  Transmit\n"
                       " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
                       "    lo: 0  0    0    0    0     0          0         0  0  0    0    0    0     0       0          0\n"
                       "  eth0: 3145728  20020    0    0    0     0          0         0  4194304  30020    0    0    0     0       0          0\n",
                return_code=0
            )
            
            mock_exec.side_effect = [
                cpuinfo_result,
                loadavg_result,
                meminfo_result,
                df_result,
                net_dev_result_1,
                net_dev_result_2,
            ]
            mock_monotonic.side_effect = [300.0, 301.0]
            
            server = MagicMock()
            metrics = collector.collect_metrics(server, "10.0.1.10")
            
            assert metrics.cpu_percent == 25.0  # (0.5/2)*100
            assert metrics.ram_percent == 25.0
            assert metrics.disk_percent == 50.0
            assert metrics.network_up_mbps == 1.0
            assert metrics.network_down_mbps == 1.0
            mock_sleep.assert_called_once_with(collector.NETWORK_SAMPLE_SECONDS)


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
             patch("src.dagdi.commands.monitoring.MetricsCollector.collect_metrics", return_value=Metrics(12.5, 25.0, 50.0, 1.0, 2.0)), \
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

        with patch("src.dagdi.commands.monitoring.MetricsCollector.collect_metrics", side_effect=fake_collect):
            results, failures = _collect_metrics_for_targets(target_servers, timeout=15)

        assert failures == []
        assert len(results) == 3
        assert [(row["server"], row["ip"]) for row in results] == [
            ("web-1", "10.0.1.10"),
            ("web-1", "10.0.1.11"),
            ("db-1", "10.0.2.10"),
        ]
        assert max_active_calls > 1
