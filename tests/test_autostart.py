"""
tests/test_autostart.py - Unit tests for Sentinel AI auto-start manager.
Validates command formatting, Windows registry interactions via mock winreg,
toggle semantics, and graceful handling across execution environments.
"""
import sys
import unittest
from pathlib import Path, WindowsPath
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.autostart import (
    _get_launch_command,
    disable_autostart,
    enable_autostart,
    is_autostart_enabled,
    toggle_autostart,
)


def _windows_path_usable() -> bool:
    """These tests patch os.name to 'nt', but pathlib dispatches Path flavour
    dynamically — on a non-Windows host, instantiating WindowsPath raises
    NotImplementedError.  They are meaningful only where Windows paths work."""
    try:
        WindowsPath("C:\\x")
        return True
    except NotImplementedError:
        return False


needs_windows_path = unittest.skipUnless(
    _windows_path_usable(), "requires Windows path semantics (Windows host)"
)


class TestAutoStart(unittest.TestCase):

    def test_launch_command_formatting_with_minimized(self):
        cmd = _get_launch_command(app_path="/test/path/app.py", start_minimized=True)
        self.assertIn("app.py", cmd)
        self.assertTrue(cmd.endswith('--minimized"') or cmd.endswith("--minimized"))

    def test_launch_command_without_minimized(self):
        cmd = _get_launch_command(app_path="/test/path/app.py", start_minimized=False)
        self.assertIn("app.py", cmd)
        self.assertNotIn("--minimized", cmd)

    @patch("os.name", "nt")
    @needs_windows_path
    def test_windows_registry_enable_success(self):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            success, msg = enable_autostart(app_path="C:\\SentinelAI\\app.py", start_minimized=True)
            self.assertTrue(success)
            self.assertIn("enabled successfully", msg.lower())
            mock_winreg.SetValueEx.assert_called_once()
            call_args = mock_winreg.SetValueEx.call_args[0]
            self.assertEqual(call_args[1], "SentinelAI")
            self.assertIn("--minimized", call_args[4])

    @patch("os.name", "nt")
    def test_windows_registry_disable_success(self):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            success, msg = disable_autostart()
            self.assertTrue(success)
            self.assertIn("disabled successfully", msg.lower())
            mock_winreg.DeleteValue.assert_called_once_with(mock_key, "SentinelAI")

    @patch("os.name", "nt")
    def test_windows_registry_is_enabled(self):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ("python.exe app.py", 1)

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            enabled = is_autostart_enabled()
            self.assertTrue(enabled)

    @patch("os.name", "nt")
    def test_windows_registry_is_disabled_when_not_found(self):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = FileNotFoundError("Key not found")

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            enabled = is_autostart_enabled()
            self.assertFalse(enabled)

    @patch("os.name", "nt")
    @needs_windows_path
    def test_toggle_autostart_workflow(self):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

        # 1. State: currently disabled -> toggle should enable
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            success, is_now_on, msg = toggle_autostart(app_path="C:\\SentinelAI\\app.py")
            self.assertTrue(success)
            self.assertTrue(is_now_on)

        # 2. State: currently enabled -> toggle should disable
        mock_winreg.QueryValueEx.side_effect = None
        mock_winreg.QueryValueEx.return_value = ("command", 1)
        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            success2, is_now_on2, msg2 = toggle_autostart()
            self.assertTrue(success2)
            self.assertFalse(is_now_on2)


if __name__ == "__main__":
    unittest.main()
