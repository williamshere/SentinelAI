from types import SimpleNamespace
from unittest.mock import patch

import sensors.processes as processes_module


class FakeProcess:
    def __init__(self, pid, name, cpu_percent, memory_bytes):
        self.info = {"pid": pid, "name": name}
        self._cpu_percent = cpu_percent
        self._memory_bytes = memory_bytes

    def cpu_percent(self, interval=None):
        return self._cpu_percent

    def memory_info(self):
        return SimpleNamespace(rss=self._memory_bytes)


def test_process_info_sorts_and_normalizes_cpu_usage():
    processes_module._last_scan_time = 0.0
    processes_module._cached_processes = []
    fake_psutil = SimpleNamespace(
        cpu_count=lambda logical=True: 4,
        virtual_memory=lambda: SimpleNamespace(total=8 * 1024**3),
        process_iter=lambda attrs: [
            FakeProcess(10, "lower.exe", 40.0, 512 * 1024**2),
            FakeProcess(20, "higher.exe", 80.0, 1024 * 1024**2),
        ],
    )

    with patch.object(processes_module, "psutil", fake_psutil), patch.object(
        processes_module.time, "monotonic", return_value=10.0
    ):
        result = processes_module.get_process_info()

    assert result["available"] is True
    assert [process["name"] for process in result["processes"]] == ["higher.exe", "lower.exe"]
    assert result["processes"][0]["cpu_percent"] == 20.0
    assert result["processes"][0]["memory_percent"] == 12.5


def test_process_info_reuses_snapshot_during_scan_interval():
    processes_module._last_scan_time = 10.0
    processes_module._cached_processes = [{"pid": 7, "name": "cached.exe"}]

    with patch.object(processes_module, "psutil", object()), patch.object(
        processes_module.time, "monotonic", return_value=12.0
    ):
        result = processes_module.get_process_info()

    assert result == {"available": True, "processes": [{"pid": 7, "name": "cached.exe"}]}


def test_process_info_reports_unavailable_without_psutil():
    with patch.object(processes_module, "psutil", None):
        assert processes_module.get_process_info() == {"available": False, "processes": []}
