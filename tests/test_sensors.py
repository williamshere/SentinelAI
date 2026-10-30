"""
tests/test_sensors.py - Unit tests for Sentinel AI telemetry sensor modules.
Validates CPU temperature and wattage metrics, dynamic TDP power curve,
calibrated thermal fallback model, elevation detection, and graceful exception handling.
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
    _estimate_cpu_temperature,
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
            "is_estimated_temp",
            "available",
        }
        self.assertTrue(expected_keys.issubset(info.keys()))
        self.assertIsInstance(info["usage"], (int, float))
        self.assertIsInstance(info["frequency"], (int, float))
        self.assertIsInstance(info["temperature"], (int, float))
        self.assertIsInstance(info["power_watts"], (int, float))
        self.assertIsInstance(info["temp_available"], bool)
        self.assertIsInstance(info["is_elevated"], bool)
        self.assertIsInstance(info["is_estimated_temp"], bool)
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

    def test_cpu_estimated_thermal_model_scaling(self):
        """Test physics-based thermal estimation across typical power envelopes."""
        # At idle (15W): ~28 C
        idle_temp = _estimate_cpu_temperature(15.0)
        self.assertGreaterEqual(idle_temp, 26.0)
        self.assertLessEqual(idle_temp, 32.0)

        # Under load (125W): ~55-65 C
        load_temp = _estimate_cpu_temperature(125.0)
        self.assertGreater(load_temp, idle_temp)
        self.assertGreaterEqual(load_temp, 54.0)
        self.assertLessEqual(load_temp, 68.0)

        # Under maximum PL2 peak (160W): ~70-80 C
        peak_temp = _estimate_cpu_temperature(160.0)
        self.assertGreater(peak_temp, load_temp)
        self.assertGreaterEqual(peak_temp, 68.0)
        self.assertLessEqual(peak_temp, 82.0)

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

            # Raw hardware query without fallback returns 0.0 and temp_available=False
            info_raw = get_cpu_info(allow_fallback=False)
            self.assertFalse(info_raw["temp_available"])
            self.assertEqual(info_raw["temperature"], 0.0)
            self.assertTrue(info_raw["available"])

            # Default query with fallback provides calibrated estimate and flags is_estimated_temp=True
            info_est = get_cpu_info(allow_fallback=True)
            self.assertFalse(info_est["temp_available"])  # Hardware driver unavailable
            self.assertTrue(info_est["is_estimated_temp"])
            self.assertGreater(info_est["temperature"], 20.0)
            self.assertEqual(info_est["temp_source"], "estimated_thermal_model")
            self.assertTrue(info_est["available"])

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
        mock_disk = MagicMock()
        mock_disk.total = 1000 * (1024 ** 3)
        mock_disk.used = 450 * (1024 ** 3)
        mock_disk.free = 550 * (1024 ** 3)
        mock_disk.percent = 45.0
        mock_psutil.disk_usage.return_value = mock_disk

        with patch.object(disk_module, "psutil", mock_psutil):
            info = get_disk_info()
            self.assertTrue({"mount", "total", "used", "free", "percent", "available"}.issubset(info))
            self.assertEqual(info["percent"], 45.0)

    def test_gpu_info_fallback(self):
        """Verify get_gpu_info gracefully degrades without throwing when NVML is missing."""
        with patch.object(gpu_module, "_ensure_nvml", return_value=False):
            info = get_gpu_info()
            self.assertIn("name", info)
            self.assertIn("usage", info)
            self.assertIn("temperature", info)
            self.assertIn("vram_used", info)
            self.assertIn("vram_total", info)
            self.assertIn("power_watts", info)
            self.assertIn("available", info)


if __name__ == "__main__":
    unittest.main()
