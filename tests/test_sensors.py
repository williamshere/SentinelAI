"""
tests/test_sensors.py - Unit tests for Sentinel AI telemetry sensor modules.
Validates CPU temperature and wattage metrics, dynamic TDP power curve,
elevation detection, and graceful exception handling across all hardware sensors.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sensors.cpu as cpu_module
import sensors.disk as disk_module
import sensors.ram as ram_module
import sensors.gpu as gpu_module

from sensors.cpu import (
    _get_cpu_power_watts,
    _get_cpu_temperature,
    get_cpu_info,
    is_admin,
)
from sensors.disk import get_disk_info, get_system_drive_mount
from sensors.gpu import get_gpu_info
from sensors.ram import get_ram_info


class TestSensors(unittest.TestCase):

    def test_cpu_info_returns_expected_keys(self):
        info = get_cpu_info()
        expected_keys = {
            "usage",
            "frequency",
            "temperature",
            "power_watts",
            "temp_available",
            "temp_source",
            "power_source",
            "is_elevated",
            "available",
        }
        self.assertTrue(expected_keys.issubset(info.keys()))
        self.assertIsInstance(info["usage"], (int, float))
        self.assertIsInstance(info["frequency"], (int, float))
        self.assertIsInstance(info["temperature"], (int, float))
        self.assertIsInstance(info["power_watts"], (int, float))
        self.assertIsInstance(info["temp_available"], bool)
        self.assertIsInstance(info["is_elevated"], bool)
        self.assertTrue(info["available"])

    def test_cpu_info_values_within_physical_bounds(self):
        info = get_cpu_info()
        self.assertGreaterEqual(info["usage"], 0.0)
        self.assertLessEqual(info["usage"], 100.0)
        self.assertGreaterEqual(info["frequency"], 0.0)
        self.assertGreaterEqual(info["temperature"], 0.0)
        self.assertLessEqual(info["temperature"], 130.0)
        self.assertGreaterEqual(info["power_watts"], 0.0)
        self.assertLessEqual(info["power_watts"], 350.0)

    def test_cpu_tdp_power_curve_scaling(self):
        """Test dynamic TDP curve scaling from idle ~15W to ~160W under 100% load."""
        watts_idle, src_idle = _get_cpu_power_watts(0.0)
        watts_mid, src_mid = _get_cpu_power_watts(50.0)
        watts_full, src_full = _get_cpu_power_watts(100.0)

        # Baseline ~15W at idle
        self.assertAlmostEqual(watts_idle, 15.0, delta=1.0)
        self.assertEqual(src_idle, "estimated_tdp_curve")

        # Intermediate load scales monotonically
        self.assertGreater(watts_mid, watts_idle)
        self.assertGreater(watts_full, watts_mid)

        # Full load should approach 160W for Intel Core i7-12700 curve
        self.assertAlmostEqual(watts_full, 160.0, delta=2.0)
        self.assertEqual(src_full, "estimated_tdp_curve")

    def test_cpu_temperature_psutil_reading(self):
        mock_psutil = MagicMock()
        mock_entry = MagicMock()
        mock_entry.current = 48.5
        mock_psutil.sensors_temperatures.return_value = {"coretemp": [mock_entry]}

        with patch.object(cpu_module, "psutil", mock_psutil):
            temp, source, err = _get_cpu_temperature()
            self.assertEqual(temp, 48.5)
            self.assertEqual(source, "psutil_coretemp")
            self.assertIsNone(err)

    def test_cpu_temperature_exception_graceful_handling(self):
        """Ensure no unhandled exception is thrown when sensor calls fail."""
        mock_psutil = MagicMock()
        mock_psutil.sensors_temperatures.side_effect = RuntimeError("Driver failure")

        with patch.object(cpu_module, "psutil", mock_psutil), patch("sensors.cpu.os.name", "nt"):
            temp, source, err = _get_cpu_temperature()
            self.assertEqual(temp, 0.0)
            self.assertEqual(source, "unavailable")
            self.assertIsNotNone(err)

            # get_cpu_info must remain safe and available
            info = get_cpu_info()
            self.assertFalse(info["temp_available"])
            self.assertEqual(info["temperature"], 0.0)
            self.assertTrue(info["available"])

    def test_admin_elevation_check(self):
        """Verify is_admin() returns a boolean without throwing exceptions."""
        admin_flag = is_admin()
        self.assertIsInstance(admin_flag, bool)

    def test_ram_info_mock_and_keys(self):
        mock_psutil = MagicMock()
        mock_mem = MagicMock()
        mock_mem.total = 32 * (1024 ** 3)
        mock_mem.used = 14 * (1024 ** 3)
        mock_mem.available = 18 * (1024 ** 3)
        mock_mem.percent = 43.75
        mock_psutil.virtual_memory.return_value = mock_mem

        with patch.object(ram_module, "psutil", mock_psutil):
            info = get_ram_info()
            self.assertTrue({"total", "used", "free", "percent"}.issubset(info))
            self.assertEqual(info["percent"], 43.75)
            self.assertEqual(info["total"], 32 * (1024 ** 3))

    def test_disk_info_mock_and_keys(self):
        mock_psutil = MagicMock()
        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 350 * (1024 ** 3)
        mock_usage.free = 650 * (1024 ** 3)
        mock_usage.percent = 35.0
        mock_psutil.disk_usage.return_value = mock_usage

        with patch.object(disk_module, "psutil", mock_psutil):
            info = get_disk_info()
            self.assertTrue({"mount", "total", "used", "free", "percent", "available"}.issubset(info))
            self.assertEqual(info["percent"], 35.0)
            self.assertTrue(info["available"])

    def test_disk_info_dynamic_mount_fallback(self):
        mount = get_system_drive_mount()
        self.assertIsInstance(mount, str)
        self.assertTrue(len(mount) > 0)

        # Invalid mount point should gracefully return empty structure
        bad_info = get_disk_info(mount_point="/non_existent_mount_xyz_123")
        self.assertFalse(bad_info["available"])
        self.assertEqual(bad_info["percent"], 0.0)

    def test_gpu_info_returns_expected_keys(self):
        info = get_gpu_info()
        expected = {"name", "usage", "temperature", "vram_used", "vram_total", "power_watts", "clock_mhz", "available"}
        self.assertTrue(expected.issubset(info))
        self.assertIsInstance(info["usage"], (int, float))
        self.assertIsInstance(info["temperature"], (int, float))
        self.assertIsInstance(info["available"], bool)


if __name__ == "__main__":
    unittest.main()
