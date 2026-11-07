"""Predictive thermal and storage estimates using configurable reference values."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("sentinel.predictive")

try:
    from config import SSD_DAILY_WRITE_GB_ESTIMATE, SSD_RATED_TBW_ESTIMATE
except ImportError:
    SSD_DAILY_WRITE_GB_ESTIMATE = 30.0
    SSD_RATED_TBW_ESTIMATE = 600.0

# Generic reference thresholds; actual limits vary by component and cooler.
AIO_360_NOMINAL_THETA = 0.21
AIO_360_WARNING_THETA = 0.29
AIO_360_CRITICAL_THETA = 0.38
GPU_HOTSPOT_NOMINAL_DELTA = 13.0
GPU_HOTSPOT_WARNING_DELTA = 19.0
GPU_HOTSPOT_CRITICAL_DELTA = 24.0


@dataclass
class PredictiveAssessment:
    cpu_thermal_resistance: float
    cooling_efficiency_percent: float
    cpu_health_status: str
    gpu_hotspot_delta: float
    gpu_contact_status: str
    ssd_health_percent: float | None
    ssd_estimated_years_remaining: float | None
    ssd_wear_status: str
    maintenance_recommendations: list[str]
    predictive_advisory: str


class PredictiveEngine:
    """
    Evaluates physical thermal interface degradation, liquid cooling pump/radiator health,
    and storage silicon endurance.
    """

    def __init__(self, ambient_c: float = 24.0):
        self.ambient_c = ambient_c

    def calculate_thermal_resistance(
        self,
        temp_c: float,
        power_watts: float,
        ambient_c: float | None = None
    ) -> float:
        """
        Calculates specific thermal resistance theta = (Temp - Ambient) / Power in °C/W.
        Requires sustained power dissipation (> 35W) to avoid idle noise.
        """
        amb = ambient_c if ambient_c is not None else self.ambient_c
        pwr = max(1.0, float(power_watts or 0.0))
        temp = float(temp_c or 0.0)

        if pwr < 30.0 or temp <= amb:
            # During low power states, return nominal calibrated baseline
            return AIO_360_NOMINAL_THETA

        theta = (temp - amb) / pwr
        return round(max(0.05, min(1.5, theta)), 3)

    def calculate_cooling_efficiency(self, theta: float) -> tuple[float, str]:
        """
        Converts thermal resistance to a 0-100% Cooling Efficiency score
        calibrated for a 360mm AIO liquid cooler.
        """
        if theta <= AIO_360_NOMINAL_THETA:
            score = 100.0
            status = "Optimal (AIO Peak Performance)"
        elif theta <= AIO_360_WARNING_THETA:
            # Linear scale from 100% down to 75%
            ratio = (theta - AIO_360_NOMINAL_THETA) / (AIO_360_WARNING_THETA - AIO_360_NOMINAL_THETA)
            score = 100.0 - (ratio * 25.0)
            status = "Good (Normal Radiator Heat Dissipation)"
        elif theta <= AIO_360_CRITICAL_THETA:
            # Linear scale from 75% down to 40%
            ratio = (theta - AIO_360_WARNING_THETA) / (AIO_360_CRITICAL_THETA - AIO_360_WARNING_THETA)
            score = 75.0 - (ratio * 35.0)
            status = "Degraded (Dust Accumulation or Paste Drying)"
        else:
            score = max(10.0, 40.0 - ((theta - AIO_360_CRITICAL_THETA) * 50.0))
            status = "Critical (Check AIO Pump RPM & Cold-Plate Mounting)"

        return round(score, 1), status

    def evaluate_gpu_hotspot(self, edge_temp: float, hotspot_temp: float | None = None) -> tuple[float, str]:
        """
        Evaluates GPU die-to-junction hotspot delta for thermal paste pump-out.
        """
        edge = float(edge_temp or 0.0)
        # If hotspot sensor is unavailable, model standard edge-to-junction spread
        hotspot = float(hotspot_temp) if hotspot_temp is not None and hotspot_temp > edge else edge + 12.5
        delta = round(hotspot - edge, 1)

        if delta <= GPU_HOTSPOT_NOMINAL_DELTA + 2.0:
            status = "Optimal Die Contact"
        elif delta <= GPU_HOTSPOT_WARNING_DELTA:
            status = "Normal Junction Spread"
        elif delta <= GPU_HOTSPOT_CRITICAL_DELTA:
            status = "Thermal Paste Pump-Out Advisory"
        else:
            status = "Severe Contact Pressure Loss"

        return delta, status

    def project_ssd_lifespan(
        self,
        wear_percent: float | None,
        rated_tbw: float = SSD_RATED_TBW_ESTIMATE,
        daily_write_gb: float = SSD_DAILY_WRITE_GB_ESTIMATE
    ) -> tuple[float | None, str]:
        """
        Roughly estimates years remaining from wear percent and generic TBW/write
        assumptions. Set rated_tbw and daily_write_gb for the specific drive/use.
        """
        if wear_percent is None or rated_tbw <= 0 or daily_write_gb <= 0:
            return None, "Unavailable (SMART wear data required)"

        wear = max(0.0, min(100.0, float(wear_percent)))
        remaining_tbw = max(0.0, rated_tbw * (1.0 - (wear / 100.0)))
        daily_tb = daily_write_gb / 1024.0
        days_left = remaining_tbw / daily_tb
        years_left = round(days_left / 365.25, 1)

        if wear < 20.0:
            status = "Low wear (rough estimate)"
        elif wear < 50.0:
            status = "Moderate wear (rough estimate)"
        elif wear < 80.0:
            status = "Aging (rough estimate)"
        else:
            status = "High wear (rough estimate) - Plan backup and replacement"

        return years_left, status

    def evaluate_system(
        self,
        metrics: dict[str, Any],
        storage_health: dict[str, Any] | None = None
    ) -> PredictiveAssessment:
        """
        Runs comprehensive predictive diagnostic synthesis across CPU, GPU, and Storage.
        """
        cpu = metrics.get("cpu", {})
        gpu = metrics.get("gpu", {})

        cpu_temp = float(cpu.get("temperature") or 0.0)
        cpu_pwr = float(cpu.get("power_watts") or 0.0)
        gpu_temp = float(gpu.get("temperature") or 0.0)

        # 1. CPU AIO Liquid Cooling Analysis
        theta = self.calculate_thermal_resistance(cpu_temp, cpu_pwr)
        cooling_eff, cpu_status = self.calculate_cooling_efficiency(theta)

        # 2. GPU Hotspot Contact Analysis
        gpu_hotspot_delta, gpu_status = self.evaluate_gpu_hotspot(gpu_temp)

        # 3. Storage Lifespan Projection
        sh = storage_health or {}

        storage_available = bool(sh.get("available", False))
        wear_pct = sh.get("wear_percent") if storage_available else None
        ssd_health = sh.get("health_percent") if storage_available else None
        ssd_years, ssd_status = self.project_ssd_lifespan(wear_pct)

        # 4. Generate Targeted Maintenance Recommendations
        recs = []
        if cooling_eff < 75.0:
            recs.append("Cooling efficiency is below the reference range. Check the cooler, airflow, and manufacturer guidance.")
        else:
            recs.append("Thermal resistance is within the generic cooling reference range; actual limits depend on the cooler.")

        if gpu_hotspot_delta > GPU_HOTSPOT_WARNING_DELTA:
            recs.append("GPU hotspot spread is elevated; compare against the GPU manufacturer's limits and monitor under load.")

        if wear_pct is None:
            recs.append("Storage SMART wear data is unavailable; lifespan cannot be estimated.")
        elif wear_pct > 70.0:
            recs.append("Storage wear is elevated. Verify the drive's SMART reserve data and maintain a current backup.")
        else:
            recs.append(
                f"Rough storage lifespan estimate: {ssd_years} years, assuming "
                f"{SSD_RATED_TBW_ESTIMATE:g} TBW endurance and {SSD_DAILY_WRITE_GB_ESTIMATE:g} GB written daily."
            )

        # 5. Formulate Diagnostic Advisory
        if cooling_eff >= 90.0 and gpu_hotspot_delta <= GPU_HOTSPOT_NOMINAL_DELTA + 3.0 and wear_pct is not None:
            advisory = (
                f"Thermal readings are within generic reference ranges ({cooling_eff}% reference efficiency, "
                f"θ = {theta:.2f}°C/W). GPU hotspot spread is within the reference range. "
                f"Storage lifespan estimate is rough and uses generic endurance/write assumptions."
            )
        elif cooling_eff < 75.0:
            advisory = (
                f"Elevated thermal resistance detected (θ = {theta:.2f}°C/W, {cooling_eff}% of the generic reference). "
                f"Check cooling and airflow against the installed hardware's manufacturer guidance."
            )
        elif wear_pct is None:
            advisory = "Storage SMART wear data is unavailable; no storage lifespan estimate can be made."
        else:
            advisory = (
                f"Thermal readings are at {cooling_eff}% of the generic cooling reference. "
                f"Rough storage lifespan estimate: {ssd_years} years using configurable generic assumptions."
            )

        return PredictiveAssessment(
            cpu_thermal_resistance=theta,
            cooling_efficiency_percent=cooling_eff,
            cpu_health_status=cpu_status,
            gpu_hotspot_delta=gpu_hotspot_delta,
            gpu_contact_status=gpu_status,
            ssd_health_percent=ssd_health,
            ssd_estimated_years_remaining=ssd_years,
            ssd_wear_status=ssd_status,
            maintenance_recommendations=recs,
            predictive_advisory=advisory,
        )
