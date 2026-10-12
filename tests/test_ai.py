"""
tests/test_ai.py - Unit tests for Sentinel AI intelligence and diagnostic subsystem.
Validates PC health scoring formulas, deterministic rule-based recommendations,
diagnostic prompt generation, and local LLM / heuristic fallback resilience.
"""
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.analyzer import HardwareAnalyzer
from ai.health import calculate_health_score
from ai.prompts import build_telemetry_prompt
from ai.recommendations import get_deterministic_recommendations


class TestHealthScore(unittest.TestCase):

    def test_health_score_optimal_baseline(self):
        metrics = {
            "cpu": {"usage": 8.0, "temperature": 42.0},
            "ram": {"percent": 15.0},
            "disk": {"percent": 20.0},
            "gpu": {
                "available": True,
                "usage": 10.0,
                "temperature": 45.0,
                "vram_used": 1 * (1024 ** 3),
                "vram_total": 12 * (1024 ** 3),
            },
        }
        res = calculate_health_score(metrics)
        self.assertGreaterEqual(res["total_score"], 90)
        self.assertEqual(res["status"], "Optimal")
        self.assertEqual(res["color"], "#34d399")
        self.assertEqual(res["thermal_score"], 100.0)

    def test_health_score_critical_thermal_throttle(self):
        metrics = {
            "cpu": {"usage": 85.0, "temperature": 94.0},
            "ram": {"percent": 50.0},
            "disk": {"percent": 40.0},
            "gpu": {
                "available": True,
                "usage": 95.0,
                "temperature": 88.0,
                "vram_used": 10 * (1024 ** 3),
                "vram_total": 12 * (1024 ** 3),
            },
        }
        res = calculate_health_score(metrics)
        # With high temperatures, thermal subscore should collapse
        self.assertLess(res["thermal_score"], 40.0)
        self.assertLess(res["total_score"], 65)
        self.assertIn(res["status"], ("Warning", "Critical"))

    def test_health_score_weight_calculation(self):
        metrics = {
            "cpu": {"usage": 20.0, "temperature": 50.0},
            "ram": {"percent": 50.0},
            "disk": {"percent": 50.0},
            "gpu": {
                "available": True,
                "usage": 20.0,
                "temperature": 50.0,
                "vram_used": 4 * (1024 ** 3),
                "vram_total": 12 * (1024 ** 3),
            },
        }
        res = calculate_health_score(metrics)
        expected_raw = (
            0.40 * res["thermal_score"]
            + 0.30 * res["memory_storage_score"]
            + 0.30 * res["headroom_score"]
        )
        self.assertEqual(res["total_score"], int(round(expected_raw)))


class TestRecommendations(unittest.TestCase):

    def test_nominal_recommendations(self):
        metrics = {
            "cpu": {"usage": 15.0, "temperature": 48.0},
            "ram": {"percent": 35.0},
            "disk": {"percent": 40.0},
            "gpu": {"available": True, "usage": 25.0, "temperature": 52.0, "vram_used": 2, "vram_total": 12},
        }
        recs = get_deterministic_recommendations(metrics)
        self.assertEqual(len(recs), 1)
        self.assertIn("optimal parameters", recs[0].lower())

    def test_cpu_thermal_recommendations(self):
        metrics = {
            "cpu": {"usage": 80.0, "temperature": 86.0},
            "ram": {"percent": 40.0},
            "disk": {"percent": 40.0},
            "gpu": {"available": False},
        }
        recs = get_deterministic_recommendations(metrics)
        self.assertTrue(any("Noctua" in r or "thermal limit critical" in r for r in recs))

    def test_gpu_and_vram_recommendations(self):
        metrics = {
            "cpu": {"usage": 10.0, "temperature": 45.0},
            "ram": {"percent": 40.0},
            "disk": {"percent": 40.0},
            "gpu": {
                "available": True,
                "usage": 98.0,
                "temperature": 84.0,
                "vram_used": 11.5 * (1024 ** 3),
                "vram_total": 12.0 * (1024 ** 3),
            },
        }
        recs = get_deterministic_recommendations(metrics)
        self.assertTrue(any("GPU Tweak III" in r or "82°C" in r for r in recs))
        self.assertTrue(any("RTX 5070 VRAM near capacity" in r or "quantize" in r for r in recs))


class TestPromptBuilder(unittest.TestCase):

    def test_build_telemetry_prompt_structure(self):
        metrics = {
            "cpu": {"usage": 22.4, "frequency": 4700.0, "temperature": 49.0, "power_watts": 62.0},
            "ram": {"percent": 42.0, "used": 14 * (1024 ** 3), "total": 32 * (1024 ** 3)},
            "disk": {"percent": 36.0, "mount": "C:\\"},
            "gpu": {
                "available": True,
                "name": "NVIDIA GeForce RTX 5070",
                "usage": 35.0,
                "temperature": 56.0,
                "clock_mhz": 2475,
                "vram_used": 4.5 * (1024 ** 3),
                "vram_total": 12.0 * (1024 ** 3),
                "power_watts": 130.0,
            },
        }
        health = {"total_score": 94, "status": "Optimal", "thermal_score": 98.0, "memory_storage_score": 90.0, "headroom_score": 92.0}
        prompt = build_telemetry_prompt(metrics=metrics, health_score=health)

        self.assertIn("CURRENT SYSTEM TELEMETRY SNAPSHOT", prompt)
        self.assertIn("NVIDIA GeForce RTX 5070", prompt)
        self.assertIn("Composite PC Health Score: 94/100", prompt)
        self.assertIn("49.0°C", prompt)

    def test_build_telemetry_prompt_with_trigger(self):
        metrics = {"cpu": {"usage": 96.0}, "ram": {"percent": 50.0}, "disk": {"percent": 50.0}, "gpu": {"available": False}}
        prompt = build_telemetry_prompt(metrics=metrics, trigger_reason="CPU Critical: 96.0%")
        self.assertIn("TRIGGERING CRITICAL ANOMALY EVENT", prompt)
        self.assertIn("CRITICAL BREACH: CPU Critical: 96.0%", prompt)


class TestHardwareAnalyzer(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_ollama_inference_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_payload = {
            "response": "OVERALL ASSESSMENT: System healthy.\nROOT-CAUSE HYPOTHESIS: Baseline.\nRECOMMENDED ACTIONS:\n- Maintain air filters"
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        analyzer = HardwareAnalyzer()
        metrics = {"cpu": {"usage": 15.0}, "ram": {"percent": 30.0}, "disk": {"percent": 20.0}, "gpu": {"available": False}}
        res = analyzer.analyze(metrics=metrics)

        self.assertTrue(res["success"])
        self.assertIn("Ollama", res["source"])
        self.assertIn("System healthy", res["assessment"])
        self.assertEqual(res["summary"], "System healthy.")

    @patch("urllib.request.urlopen")
    def test_ollama_failure_graceful_fallback(self, mock_urlopen):
        # Simulate network error / Ollama offline
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        analyzer = HardwareAnalyzer()
        metrics = {
            "cpu": {"usage": 85.0, "temperature": 82.0},
            "ram": {"percent": 50.0},
            "disk": {"percent": 40.0},
            "gpu": {"available": False},
        }
        health = {"total_score": 68, "status": "Warning"}
        res = analyzer.analyze(metrics=metrics, health_score=health, trigger_reason="CPU High: 85.0%")

        # Must not raise an exception, must return resilient heuristic evaluation
        self.assertTrue(res["success"])
        self.assertEqual(res["source"], "Sentinel Heuristic Engine (Local Fallback)")
        self.assertEqual(res["model"], "Rule-Based")
        self.assertIn("Triggered by CPU High: 85.0%", res["assessment"])
        self.assertIn("RECOMMENDED ACTIONS:", res["assessment"])


if __name__ == "__main__":
    unittest.main()
