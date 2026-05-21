"""Metrics collection from remote servers via SSH."""

import re
import time
from dataclasses import dataclass
from typing import Optional

from dagdi.models import Server, ExecutionResult
from dagdi.ssh.executor import execute_command


@dataclass
class Metrics:
    """System metrics collected from a server."""

    cpu_percent: float  # CPU usage percentage
    ram_percent: float  # RAM usage percentage
    disk_percent: float  # Disk usage percentage
    network_up_mbps: float  # Network upload in MB/s
    network_down_mbps: float  # Network download in MB/s


class MetricsCollector:
    """Collects system metrics from remote servers."""
    NETWORK_SAMPLE_SECONDS = 1.0

    @staticmethod
    def _raise_on_transport_error(result: ExecutionResult, metric_name: str) -> None:
        """Raise when command execution failed at transport/auth layer."""
        if result.error:
            raise RuntimeError(f"{metric_name} collection failed: {result.error}")

    def collect_metrics(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> Metrics:
        """Collect CPU, RAM, Disk, and Network metrics from a server.

        Args:
            server: Server object with SSH configuration
            ip: IP address to connect to
            timeout: SSH timeout in seconds

        Returns:
            Metrics object with collected metrics

        Raises:
            Exception: If metrics collection fails
        """
        # Collect CPU metrics
        cpu_percent = self._collect_cpu_metrics(server, ip, timeout)

        # Collect RAM metrics
        ram_percent = self._collect_ram_metrics(server, ip, timeout)

        # Collect Disk metrics
        disk_percent = self._collect_disk_metrics(server, ip, timeout)

        # Collect Network metrics
        network_up, network_down = self._collect_network_metrics(server, ip, timeout)

        return Metrics(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            disk_percent=disk_percent,
            network_up_mbps=network_up,
            network_down_mbps=network_down,
        )

    def _collect_cpu_metrics(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> float:
        """Collect CPU usage percentage.

        Parses /proc/cpuinfo to calculate CPU usage.

        Args:
            server: Server object with SSH configuration
            ip: IP address to connect to
            timeout: SSH timeout in seconds

        Returns:
            CPU usage as percentage (0-100)
        """
        # Get CPU info
        result = execute_command(server, ip, "cat /proc/cpuinfo", timeout=timeout)
        self._raise_on_transport_error(result, "CPU")

        if result.return_code != 0:
            return 0.0

        # Count CPU cores
        cpu_count = len(re.findall(r"processor\s*:", result.stdout))
        if cpu_count == 0:
            cpu_count = 1

        # Get load average (1-minute average)
        load_result = execute_command(
            server, ip, "cat /proc/loadavg", timeout=timeout
        )
        self._raise_on_transport_error(load_result, "CPU")

        if load_result.return_code != 0:
            return 0.0

        try:
            load_avg = float(load_result.stdout.split()[0])
            # Calculate percentage: (load_avg / cpu_count) * 100
            cpu_percent = min((load_avg / cpu_count) * 100, 100.0)
            return round(cpu_percent, 1)
        except (ValueError, IndexError):
            return 0.0

    def _collect_ram_metrics(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> float:
        """Collect RAM usage percentage.

        Parses /proc/meminfo to calculate RAM usage.

        Args:
            server: Server object with SSH configuration
            ip: IP address to connect to
            timeout: SSH timeout in seconds

        Returns:
            RAM usage as percentage (0-100)
        """
        result = execute_command(server, ip, "cat /proc/meminfo", timeout=timeout)
        self._raise_on_transport_error(result, "RAM")

        if result.return_code != 0:
            return 0.0

        try:
            lines = result.stdout.split("\n")
            mem_info = {}

            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = int(value.split()[0])
                    mem_info[key] = value

            total = mem_info.get("MemTotal", 1)
            available = mem_info.get("MemAvailable", 0)
            used = total - available

            ram_percent = (used / total) * 100 if total > 0 else 0.0
            return round(ram_percent, 1)
        except (ValueError, KeyError):
            return 0.0

    def _collect_disk_metrics(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> float:
        """Collect Disk usage percentage.

        Uses df command to get disk usage for root filesystem.

        Args:
            server: Server object with SSH configuration
            ip: IP address to connect to
            timeout: SSH timeout in seconds

        Returns:
            Disk usage as percentage (0-100)
        """
        result = execute_command(server, ip, "df -h /", timeout=timeout)
        self._raise_on_transport_error(result, "Disk")

        if result.return_code != 0:
            return 0.0

        try:
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return 0.0

            # Parse the second line (first is header)
            parts = lines[1].split()
            if len(parts) < 5:
                return 0.0

            # Extract percentage (e.g., "45%")
            percent_str = parts[4].rstrip("%")
            disk_percent = float(percent_str)
            return round(disk_percent, 1)
        except (ValueError, IndexError):
            return 0.0

    def _collect_network_metrics(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> tuple[float, float]:
        """Collect Network metrics (upload and download) as MB/s.

        Args:
            server: Server object with SSH configuration
            ip: IP address to connect to
            timeout: SSH timeout in seconds

        Returns:
            Tuple of (upload_mbps, download_mbps)
        """
        recv_1, sent_1 = self._read_network_counters(server, ip, timeout)
        start = time.monotonic()
        time.sleep(self.NETWORK_SAMPLE_SECONDS)
        recv_2, sent_2 = self._read_network_counters(server, ip, timeout)
        elapsed = max(time.monotonic() - start, 0.001)

        recv_delta = max(recv_2 - recv_1, 0)
        sent_delta = max(sent_2 - sent_1, 0)

        upload_mbps = round((sent_delta / elapsed) / (1024 * 1024), 2)
        download_mbps = round((recv_delta / elapsed) / (1024 * 1024), 2)

        return upload_mbps, download_mbps

    def _read_network_counters(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> tuple[int, int]:
        """Read cumulative network counters from /proc/net/dev."""
        result = execute_command(server, ip, "cat /proc/net/dev", timeout=timeout)
        self._raise_on_transport_error(result, "Network")
        if result.return_code != 0:
            return 0, 0

        try:
            lines = result.stdout.split("\n")
            total_recv = 0
            total_sent = 0

            for line in lines[2:]:
                if ":" not in line:
                    continue

                parts = line.split()
                if len(parts) < 10:
                    continue

                if_name = parts[0].rstrip(":")
                if if_name == "lo":
                    continue

                total_recv += int(parts[1])
                total_sent += int(parts[9])

            return total_recv, total_sent
        except (ValueError, IndexError):
            return 0, 0
