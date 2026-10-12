"""
tests/test_utilities.py - Unit tests for Sentinel AI system utilities.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.utilities import clean_disk_temp, clean_ram, relaunch_as_admin


class TestUtilities(unittest.TestCase):

    @unittest.skipUnless(
        os.environ.get("SENTINEL_RUN_DESTRUCTIVE_TESTS") == "1",
        "destructive: cleans the machine's real temp directory; "
        "set SENTINEL_RUN_DESTRUCTIVE_TESTS=1 to run it",
    )
    def test_clean_disk_temp_execution(self):
        success, msg, freed = clean_disk_temp()
        self.assertTrue(success)
        self.assertIn("Cleaned", msg)
        self.assertGreaterEqual(freed, 0.0)

    @patch("os.name", "posix")
    def test_clean_ram_posix_fallback(self):
        success, msg, freed = clean_ram()
        self.assertTrue(success)
        self.assertIn("simulated", msg)
        self.assertEqual(freed, 0.0)

    @patch("os.name", "posix")
    def test_relaunch_as_admin_non_nt(self):
        res = relaunch_as_admin()
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
