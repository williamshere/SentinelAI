"""
tests/test_predictive.py - Comprehensive unit tests for Sentinel AI Predictive Hardware Failure Analysis.
Covers thermal degradation calculations, 360mm AIO calibration, GPU hotspot evaluation,
NVMe lifespan projections, and SQLite database baseline persistence.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.predictive import (
    AIO_360_CRITICAL_THETA,
    AIO_360_NOMINAL_THETA,
    AIO_360_WARNING_THETA,
    GPU_HOTSPOT_CRITICAL_DELTA,
    GPU_HOTSPOT_NOMINAL_DELTA,
    GPU_HOTSPOT_WARNING_DELTA,
    PredictiveAssessment,
    PredictiveEngine,
)
from database.manager import DatabaseManager
from sensors.storage_health import get_storage_health


class TestPredictiveEngine(unittest.TestCase):

    def setUp(self):
        self.engine = PredictiveEngine(ambient_c=24.0)

    def test_thermal_resistance_low_power_fallback(self):
        # Under low power (<30W), returns nominal AIO baseline to avoid noise
        theta = self.engine.calculate_thermal_resistance(temp_c=35.0, power_watts=15.0)
        self.assertEqual(theta, AIO_360_NOMINAL_THETA)

    def test_thermal_resistance_sustained_load(self):
        # Sustained load: 60°C at 150W (ambient 24°C) -> (60-24)/150 = 36/150 = 0.24 °C/W
        theta = self.engine.calculate_thermal_resistance(temp_c=60.0, power_watts=150.0)
        self.assertAlmostEqual(theta, 0.24, places=2)

    def test_cooling_efficiency_scaling(self):
        # Nominal resistance yields 100% efficiency
        eff_nominal, status_nom = self.engine.calculate_cooling_efficiency(AIO_360_NOMINAL_THETA)
        self.assertEqual(eff_nominal, 100.0)
        self.assertIn("Optimal", status_nom)

        # Warning threshold (0.29 °C/W) yields 75% efficiency
        eff_warn, status_warn = self.engine.calculate_cooling_efficiency(AIO_360_WARNING_THETA)
        self.assertAlmostEqual(eff_warn, 75.0, places=1)

        # Critical threshold (0.38 °C/W) yields 40% efficiency
        eff_crit, status_crit = self.engine.calculate_cooling_efficiency(AIO_360_CRITICAL_THETA)
        self.assertAlmostEqual(eff_crit, 40.0, places=1)

    def test_gpu_hotspot_evaluation(self):
        # Healthy contact: edge 60°C, hotspot 72°C -> delta 12°C
        delta, status = self.engine.evaluate_gpu_hotspot(edge_temp=60.0, hotspot_temp=72.0)
        self.assertEqual(delta, 12.0)
        self.assertEqual(status, "Optimal Die Contact")

        # Early pump-out: edge 65°C, hotspot 84°C -> delta 19°C
        delta_warn, status_warn = self.engine.evaluate_gpu_hotspot(edge_temp=65.0, hotspot_temp=84.0)
        self.assertEqual(delta_warn, 19.0)
        self.assertEqual(status_warn, "Normal Junction Spread")

        # Severe degradation: edge 65°C, hotspot 90°C -> delta 25°C
        delta_crit, status_crit = self.engine.evaluate_gpu_hotspot(edge_temp=65.0, hotspot_temp=90.0)
        self.assertEqual(delta_crit, 25.0)
        self.assertEqual(status_crit, "Severe Contact Pressure Loss")

    def test_ssd_lifespan_projection(self):
        # 5% wear on 600 TBW rated drive -> remaining 570 TBW
        years, status = self.engine.project_ssd_lifespan(wear_percent=5.0, rated_tbw=600.0, daily_write_gb=30.0)
        self.assertGreater(years, 40.0)
        self.assertEqual(status, "Pristine NAND Flash Endurance")

        # 85% wear -> high wear advisory
        years_worn, status_worn = self.engine.project_ssd_lifespan(wear_percent=85.0, rated_tbw=600.0, daily_write_gb=30.0)
        self.assertLess(years_worn, 10.0)
        self.assertIn("High Wear", status_worn)

    def test_full_system_synthesis(self):
        metrics = {
            "cpu": {"temperature": 55.0, "power_watts": 135.0, "usage": 65.0},
            "gpu": {"temperature": 58.0, "power_watts": 195.0, "usage": 85.0}
        }
        storage = {
            "model": "Samsung 990 Pro 1TB",
            "wear_percent": 3.0,
            "health_percent": 97.0,
            "tbw_terabytes": 15.2
        }
        assessment = self.engine.evaluate_system(metrics, storage)
        self.assertIsInstance(assessment, PredictiveAssessment)
        self.assertGreater(assessment.cooling_efficiency_percent, 80.0)
        self.assertGreater(len(assessment.maintenance_recommendations), 0)
        self.assertIn("Cooler Master Liquid 360", assessment.predictive_advisory)

    def test_storage_health_sensor(self):
        sh = get_storage_health("C:")
        self.assertIn("health_percent", sh)
        self.assertIn("wear_percent", sh)
        self.assertIn("model", sh)
        self.assertIsInstance(sh["available"], bool)

    def test_database_predictive_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_unit_pred_final.db"
            db = DatabaseManager(db_path=db_path)

            # Test baseline recording
            b_id = db.record_hardware_baseline("cpu", 7, 0.22, 58.0, 0.0, 0.0, 100)
            self.assertGreater(b_id, 0)
            baselines = db.get_hardware_baselines("cpu")
            self.assertEqual(len(baselines), 1)

            # Test event recording
            e_id = db.record_predictive_event("cooling_efficiency", "advisory", 12.0, 45, "Clean top radiator mesh")
            self.assertGreater(e_id, 0)
            events = db.get_recent_predictive_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["category"], "cooling_efficiency")


if __name__ == "__main__":
    unittest.main()
