"""
tests/test_chat_engine.py - Unit tests for Sentinel AI 'Ask Sentinel' Conversational AI Chat.
Validates system context injection, multi-turn history tracking, LM Studio / OpenAI payload parsing,
dynamic model autodiscovery, and offline heuristic fallback.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import sys

# Ensure project root is in sys.path (matches the other test modules)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.chat_engine import BASE_SYSTEM_INSTRUCTIONS, ChatEngine


class TestChatEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ChatEngine(
            lm_studio_url="http://127.0.0.1:1234/v1",
            ollama_url="http://127.0.0.1:11434",
            model="gemma-2-9b-it",
            timeout_seconds=5.0
        )

    def test_system_context_builder(self):
        metrics = {
            "cpu": {"usage": 15.5, "frequency": 4200.0, "temperature": 48.0, "power_watts": 65.0},
            "gpu": {"usage": 45.0, "temperature": 52.0, "vram_used": 4 * 1024**3, "vram_total": 12 * 1024**3,
                    "power_watts": 140.0, "clock_mhz": 2400, "available": True},
            "ram": {"percent": 42.0, "used": 13.4 * 1024**3, "total": 32 * 1024**3},
            "disk": {"percent": 65.0},
        }
        predictive_data = {
            "cooling_efficiency": 96.5,
            "thermal_resistance": 0.215,
            "hotspot_delta": 12.0,
            "ssd_years": 48.0,
        }
        recent_sessions = [
            {"game_title": "Overwatch 2", "duration_seconds": 1800, "max_gpu_temp": 64.0, "max_cpu_temp": 62.0, "max_gpu_power_watts": 210.0}
        ]

        context = self.engine.build_system_context(
            metrics=metrics,
            predictive_data=predictive_data,
            recent_sessions=recent_sessions,
        )

        self.assertIn("Intel Core i7-12700", context)
        self.assertIn("Gigabyte Z790 Aorus Elite AX", context)
        self.assertIn("Cooler Master MasterLiquid 360", context)
        self.assertIn("RTX 5070", context)
        self.assertIn("48.0°C", context)
        self.assertIn("96.5%", context)
        self.assertIn("Overwatch 2", context)

    def test_multi_turn_history_and_clear(self):
        self.assertEqual(len(self.engine.history), 0)
        self.engine.history.append({"role": "user", "content": "Hello"})
        self.engine.history.append({"role": "assistant", "content": "Hi there"})
        self.assertEqual(len(self.engine.history), 2)

        self.engine.clear_history()
        self.assertEqual(len(self.engine.history), 0)

    @patch("ai.chat_engine.is_port_open", return_value=True)
    @patch("urllib.request.urlopen")
    def test_lm_studio_successful_query(self, mock_urlopen, mock_probe):

        mock_response_data = {
            "id": "chatcmpl-test",
            "model": "gemma-2-9b-it",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "• Cooler Master Liquid 360 AIO is maintaining 96% efficiency.\n• Liquid coolant dissipation is optimal."
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.status = 200
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        res = self.engine.ask("How is my cooler doing?", system_context="Context info")
        self.assertTrue(res["success"])
        self.assertIn("LM Studio (gemma-2-9b-it)", res["source"])
        self.assertIn("96% efficiency", res["content"])
        self.assertEqual(len(self.engine.history), 2)

    @patch("ai.chat_engine.is_port_open", return_value=False)
    def test_heuristic_offline_fallback(self, mock_probe):
        # Hermetic: no real socket connects, so this passes whether or not
        # LM Studio / Ollama happen to be running on the test machine.
        res = self.engine.ask("What is my GPU status?", system_context="Context info")
        self.assertTrue(res["success"])
        self.assertIn("RTX 5070", res["content"])
        self.assertEqual(res["source"], "Sentinel Core (Built-in Diagnostics)")
        self.assertEqual(len(self.engine.history), 2)


if __name__ == "__main__":
    unittest.main()
