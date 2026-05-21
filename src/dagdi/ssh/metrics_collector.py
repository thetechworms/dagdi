"""Metrics collection from remote servers via SSH.

Collects CPU, RAM, Disk, and Network metrics in a single SSH round-trip
by batching all reads into one shell command with section markers.
"""

import re
from dataclasses import dataclass
from typing import Optional

from dagdi.models import Server, ExecutionResult
from dagdi.ssh.executor import execute_command

NETWORK_SAMPLE_SECONDS = 0.3

_BATCH_COMMAND = (
    'echo "===CPUINFO==="; cat /proc/cpuinfo; '
    'echo "===LOADAVG==="; cat /proc/loadavg; '
    'echo "===MEMINFO==="; cat /proc/meminfo; '
    'echo "===DISK==="; df -h /; '
    'echo "===NET1==="; cat /proc/net/dev; '
    f'sleep {NETWORK_SAMPLE_SECONDS}; '
    'echo "===NET2==="; cat /proc/net/dev'
)


@dataclass
class Metrics:
    """System metrics collected from a server."""

    cpu_percent: float
    ram_percent: float
    disk_percent: float
    network_up_mbps: float
    network_down_mbps: float


class MetricsCollector:
    """Collects system metrics from remote servers."""

    NETWORK_SAMPLE_SECONDS = NETWORK_SAMPLE_SECONDS

    def collect_metrics(
        self, server: Server, ip: str, timeout: Optional[int] = None
    ) -> Metrics:
        """Collect all metrics in a single SSH round-trip."""
        result = execute_command(server, ip, _BATCH_COMMAND, timeout=timeout)
        if result.error:
            raise RuntimeError(f"Metrics collection failed: {result.error}")
        if result.return_code != 0:
            return Metrics(0.0, 0.0, 0.0, 0.0, 0.0)

        sections = self._parse_sections(result.stdout)

        cpu = self._parse_cpu(sections.get("CPUINFO", ""), sections.get("LOADAVG", ""))
        ram = self._parse_ram(sections.get("MEMINFO", ""))
        disk = self._parse_disk(sections.get("DISK", ""))
        net_up, net_down = self._parse_network(
            sections.get("NET1", ""), sections.get("NET2", "")
        )

        return Metrics(cpu, ram, disk, net_up, net_down)

    @staticmethod
    def _parse_sections(output: str) -> dict[str, str]:
        """Split batch command output into named sections."""
        sections: dict[str, str] = {}
        current_name: Optional[str] = None
        current_lines: list[str] = []

        for line in output.split("\n"):
            stripped = line.strip()
            if stripped.startswith("===") and stripped.endswith("===") and len(stripped) > 6:
                if current_name is not None:
                    sections[current_name] = "\n".join(current_lines)
                current_name = stripped.strip("=")
                current_lines = []
            else:
                current_lines.append(line)

        if current_name is not None:
            sections[current_name] = "\n".join(current_lines)

        return sections

    @staticmethod
    def _parse_cpu(cpuinfo: str, loadavg: str) -> float:
        """Parse CPU percentage from cpuinfo and loadavg text."""
        cpu_count = len(re.findall(r"processor\s*:", cpuinfo))
        if cpu_count == 0:
            cpu_count = 1

        try:
            load_avg = float(loadavg.split()[0])
            return round(min((load_avg / cpu_count) * 100, 100.0), 1)
        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def _parse_ram(meminfo: str) -> float:
        """Parse RAM percentage from meminfo text."""
        try:
            mem: dict[str, int] = {}
            for line in meminfo.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    mem[key.strip()] = int(value.split()[0])

            total = mem.get("MemTotal", 1)
            available = mem.get("MemAvailable", 0)
            return round(((total - available) / total) * 100, 1) if total > 0 else 0.0
        except (ValueError, KeyError):
            return 0.0

    @staticmethod
    def _parse_disk(df_output: str) -> float:
        """Parse disk percentage from df output text."""
        try:
            lines = df_output.strip().split("\n")
            if len(lines) < 2:
                return 0.0
            parts = lines[1].split()
            if len(parts) < 5:
                return 0.0
            return round(float(parts[4].rstrip("%")), 1)
        except (ValueError, IndexError):
            return 0.0

    @staticmethod
    def _parse_network_counters(text: str) -> tuple[int, int]:
        """Sum receive/transmit byte counters from /proc/net/dev text."""
        total_recv = 0
        total_sent = 0
        for line in text.split("\n"):
            if ":" not in line:
                continue
            parts = line.split()
            if len(parts) < 10:
                continue
            if parts[0].rstrip(":") == "lo":
                continue
            try:
                total_recv += int(parts[1])
                total_sent += int(parts[9])
            except (ValueError, IndexError):
                continue
        return total_recv, total_sent

    @staticmethod
    def _parse_network(net1: str, net2: str) -> tuple[float, float]:
        """Parse network throughput from two /proc/net/dev snapshots."""
        try:
            recv1, sent1 = MetricsCollector._parse_network_counters(net1)
            recv2, sent2 = MetricsCollector._parse_network_counters(net2)

            recv_delta = max(recv2 - recv1, 0)
            sent_delta = max(sent2 - sent1, 0)

            upload = round((sent_delta / NETWORK_SAMPLE_SECONDS) / (1024 * 1024), 2)
            download = round((recv_delta / NETWORK_SAMPLE_SECONDS) / (1024 * 1024), 2)
            return upload, download
        except (ValueError, IndexError):
            return 0.0, 0.0
