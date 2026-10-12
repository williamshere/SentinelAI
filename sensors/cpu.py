"""
sensors/cpu.py - CPU utilization, frequency, temperature, and wattage telemetry module.
Hardened against COM threading leaks and crashes during extended runtimes.
"""
import os
import time

try:
    from config import WMI_SENSOR_INTERVAL_SECONDS
except ImportError:
    WMI_SENSOR_INTERVAL_SECONDS = 15.0

_last_wmi_retry = 0.0
_wmi_available = None
_wmi_sensor_cache = {"timestamp": 0.0, "temperature": 0.0, "power_watts": 0.0, "source": "unavailable"}

try:
    import psutil
except ImportError:
    psutil = None


def is_admin() -> bool:
    """Check if current process has administrative / elevated privileges."""
    if os.name == "nt":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    else:
        try:
            return os.geteuid() == 0
        except Exception:
            return False


def _read_wmi_cpu_sensors() -> dict:
    """Read CPU temperature and power in one throttled, balanced WMI call.

    WMI enumeration is slow enough to cause visible stutter if it runs for every
    telemetry refresh.  Pairing CoInitialize/CoUninitialize also prevents the
    per-thread COM reference leak that accumulated in the previous loop.
    """
    global _last_wmi_retry, _wmi_available, _wmi_sensor_cache
    now = time.monotonic()
    if now - _wmi_sensor_cache["timestamp"] < WMI_SENSOR_INTERVAL_SECONDS:
        return _wmi_sensor_cache

    _wmi_sensor_cache = {"timestamp": now, "temperature": 0.0, "power_watts": 0.0, "source": "unavailable"}
    if os.name != "nt" or (_wmi_available is False and now - _last_wmi_retry < 60.0):
        return _wmi_sensor_cache

    # Libre/Open Hardware Monitor namespaces require elevation on typical
    # Windows installs. Avoid a costly failed COM/WMI round trip every minute
    # for a standard-user dashboard session.
    if not is_admin():
        _wmi_available = False
        return _wmi_sensor_cache

    _last_wmi_retry = now
    pythoncom = None
    initialized_com = False
    try:
        import pythoncom as _pythoncom
        import wmi
        pythoncom = _pythoncom
        pythoncom.CoInitialize()
        initialized_com = True
        for namespace, source in (("root\\LibreHardwareMonitor", "wmi_lhm"), ("root\\OpenHardwareMonitor", "wmi_ohm")):
            try:
                sensors = wmi.WMI(namespace=namespace).Sensor()
            except Exception:
                continue
            for sensor in sensors:
                sensor_type = str(getattr(sensor, "SensorType", "")).lower()
                name = str(getattr(sensor, "Name", "")).upper()
                value = float(getattr(sensor, "Value", 0.0) or 0.0)
                if sensor_type == "temperature" and "CPU" in name and 0.0 < value < 130.0:
                    _wmi_sensor_cache["temperature"] = round(value, 1)
                elif sensor_type == "power" and ("CPU PACKAGE" in name or "CPU POWER" in name) and value > 0.0:
                    _wmi_sensor_cache["power_watts"] = round(value, 1)
            if _wmi_sensor_cache["temperature"] or _wmi_sensor_cache["power_watts"]:
                _wmi_sensor_cache["source"] = source
                _wmi_available = True
                break
        if _wmi_available is None:
            _wmi_available = False
    except Exception:
        _wmi_available = False
    finally:
        if initialized_com and pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
    return _wmi_sensor_cache


def _get_cpu_temperature() -> tuple[float, str, str | None]:
    """
    Retrieve CPU package or core temperature in Celsius with cross-platform fallbacks.
    Returns: (temperature_celsius, sensor_source, error_detail)
    """
    # 1. psutil hardware sensor temperatures
    if psutil is not None:
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ("coretemp", "k10temp", "cpu_thermal", "cpu-thermal", "soc_thermal"):
                        if key in temps and temps[key]:
                            val = float(temps[key][0].current)
                            if 0.0 < val < 130.0:
                                return round(val, 1), f"psutil_{key}", None
                    for sensor_name, entries in temps.items():
                        if "cpu" in sensor_name.lower() and entries:
                            val = float(entries[0].current)
                            if 0.0 < val < 130.0:
                                return round(val, 1), f"psutil_{sensor_name}", None
                    for sensor_name, entries in temps.items():
                        if entries:
                            val = float(entries[0].current)
                            if 0.0 < val < 130.0:
                                return round(val, 1), f"psutil_{sensor_name}", None
        except Exception:
            pass

    # 2. Throttled Windows WMI fallback (shared with power telemetry).
    wmi_values = _read_wmi_cpu_sensors()
    if wmi_values["temperature"] > 0.0:
        return wmi_values["temperature"], wmi_values["source"], None

    if os.name == "nt" and not is_admin():
        return 0.0, "unavailable", "Administrator privileges required to access LibreHardwareMonitor WMI temperature sensors on Windows."

    return 0.0, "unavailable", "No hardware temperature sensors reported by OS drivers or WMI."


def _get_cpu_power_watts(usage_percent: float) -> tuple[float, str]:
    """
    Retrieve CPU package power in Watts via WMI or dynamic utilization TDP curve.
    Returns: (power_watts, power_source)
    """
    wmi_values = _read_wmi_cpu_sensors()
    if wmi_values["power_watts"] > 0.0:
        return wmi_values["power_watts"], f"{wmi_values['source']}_power"

    # Dynamic TDP curve for Intel Core i7-12700 (15W idle up to ~160W full PL2)
    try:
        pct = max(0.0, min(100.0, float(usage_percent or 0.0)))
        estimated_watts = round(15.0 + (pct / 100.0) ** 1.35 * 145.0, 1)
        return estimated_watts, "estimated_tdp_curve"
    except Exception:
        return 0.0, "unavailable"


def get_cpu_info() -> dict:
    """Fetch unified CPU usage, frequency, temperature, and wattage consumption."""
    usage = 0.0
    frequency = 0.0
    if psutil is not None:
        try:
            usage = float(psutil.cpu_percent(interval=None))
        except Exception:
            usage = 0.0

        try:
            freq = psutil.cpu_freq()
            frequency = float(freq.current if freq and freq.current is not None else 0.0)
        except Exception:
            frequency = 0.0

    temperature, temp_source, temp_error = _get_cpu_temperature()
    power_watts, power_source = _get_cpu_power_watts(usage)

    return {
        "usage": usage,
        "frequency": frequency,
        "temperature": temperature,
        "power_watts": power_watts,
        "temp_source": temp_source,
        "power_source": power_source,
        "temp_error": temp_error,
        "is_elevated": is_admin(),
        "temp_available": (temperature > 0.0),
        "available": True,
    }
