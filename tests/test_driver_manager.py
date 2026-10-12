"""
tests/test_driver_manager.py - Unit tests for Sentinel AI Driver & Firmware Manager.
Validates driver inventory scanning, subsystem categorization, and PnP update triggers.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.driver_manager import DriverManager


class TestDriverManager(unittest.TestCase):

    def setUp(self):
        self.dm = DriverManager()

    def test_scan_drivers_structure(self):
        drivers = self.dm.scan_drivers()
        self.assertIsInstance(drivers, list)
        self.assertGreater(len(drivers), 0)

        for d in drivers:
            self.assertIn("device_name", d)
            self.assertIn("category", d)
            self.assertIn("version", d)
            self.assertIn("driver_date", d)
            self.assertIn("status", d)

    def test_display_driver_is_reported_when_present(self):
        drivers = self.dm.scan_drivers()
        gpu_drivers = [d for d in drivers if "5070" in d["device_name"] or "Display" in d["category"]]
        for gpu in gpu_drivers:
            self.assertIn("Display", gpu["category"])

    def test_format_driver_entries_categorization(self):
        raw_items = [
            {"DeviceName": "NVIDIA RTX 5070", "DeviceClass": "Display", "DriverVersion": "572.16", "DriverDate": "20260815000000.000000-000"},
            {"DeviceName": "Intel Wi-Fi 6E", "DeviceClass": "Net", "DriverVersion": "23.40.0.4", "DriverDate": "20260510000000.000000-000"},
            {"DeviceName": "NVMe Controller", "DeviceClass": "SCSIAdapter", "DriverVersion": "10.0.1", "DriverDate": "20260101000000.000000-000"},
        ]
        formatted = self.dm._format_driver_entries(raw_items)
        self.assertEqual(len(formatted), 3)
        self.assertEqual(formatted[0]["category"], "Display / GPU")
        self.assertEqual(formatted[1]["category"], "Network / LAN")
        self.assertEqual(formatted[2]["category"], "Storage Controller")
        self.assertEqual(formatted[0]["driver_date"], "2026081500")

    def test_scan_hardware_changes(self):
        ok, msg = self.dm.scan_for_hardware_changes()
        self.assertTrue(ok)
        self.assertIn("scan", msg.lower())


if __name__ == "__main__":
    unittest.main()
