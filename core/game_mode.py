"""
core/game_mode.py - Intelligent Game Mode and Gaming Session Telemetry Tracker.
Monitors system processes for active games (e.g. Overwatch 2, Marvel Rivals),
activates Do-Not-Disturb notification suppression, and aggregates high-fidelity
thermal, power, and clock stability metrics for post-game performance reporting.
"""
from __future__ import annotations

import datetime
from collections import deque
from dataclasses import dataclass
import logging
from typing import Callable

logger = logging.getLogger("sentinel.game_mode")

KNOWN_GAME_PROCESSES: dict[str, str] = {
    # Blizzard / Overwatch
    "overwatch.exe": "Overwatch 2",
    "overwatch_test.exe": "Overwatch 2 (PTR)",
    # Marvel Rivals
    "marvelrivals.exe": "Marvel Rivals",
    "marvel-win64-shipping.exe": "Marvel Rivals",
    # Riot Games
    "valorant.exe": "Valorant",
    "valorant-win64-shipping.exe": "Valorant",
    "league of legends.exe": "League of Legends",
    # Valve
    "cs2.exe": "Counter-Strike 2",
    "dota2.exe": "Dota 2",
    # Grinding Gear Games
    "pathofexile.exe": "Path of Exile",
    "pathofexile_x64.exe": "Path of Exile",
    "pathofexilesteam.exe": "Path of Exile",
    "pathofexile2.exe": "Path of Exile 2",
    # Popular High-Fidelity Titles
    "cyberpunk2077.exe": "Cyberpunk 2077",
    "eldenring.exe": "Elden Ring",
    "starfield.exe": "Starfield",
    "helldivers2.exe": "Helldivers 2",
    "baldursgate3.exe": "Baldur's Gate 3",
    "bg3.exe": "Baldur's Gate 3",
    "blackmythwukong.exe": "Black Myth: Wukong",
    "apexlegends.exe": "Apex Legends",
    "r5apex.exe": "Apex Legends",
    "fortniteclient-win64-shipping.exe": "Fortnite",
}

# At the normal two-second telemetry cadence, this keeps six hours of samples.
# It prevents an unattended/manual session from growing memory without bound.
MAX_SESSION_SAMPLES = 10_800


@dataclass
class GamingSessionSummary:
    session_id: int | None
    game_title: str
    process_name: str
    start_time: str
    end_time: str
    duration_seconds: int
    duration_formatted: str
    avg_cpu_temp: float
    max_cpu_temp: float
    avg_gpu_temp: float
    max_gpu_temp: float
    avg_cpu_power_watts: float
    max_cpu_power_watts: float
    avg_gpu_power_watts: float
    max_gpu_power_watts: float
    avg_cpu_usage: float
    max_cpu_usage: float
    avg_gpu_usage: float
    max_gpu_usage: float
    throttle_incidents: int
    thermal_headroom_c: float
    health_score_impact: float


class GameModeManager:
    """
    Manages Game Mode lifecycle, auto-detection of gaming executables,
    telemetry sampling during active sessions, and aggregation of session statistics.
    """
    def __init__(
        self,
        db_manager=None,
        alert_manager=None,
        on_game_start_callback: Callable[[str], None] | None = None,
        on_game_end_callback: Callable[[GamingSessionSummary], None] | None = None,
    ):
        self.db_manager = db_manager
        self.alert_manager = alert_manager
        self.on_game_start = on_game_start_callback
        self.on_game_end = on_game_end_callback

        self.is_active: bool = False
        self.current_game: str | None = None
        self.current_process: str | None = None
        self.session_id: int | None = None
        self.session_start_time: datetime.datetime | None = None
        self.manual_override: bool | None = None

        self.samples: deque[dict] = deque(maxlen=MAX_SESSION_SAMPLES)
        self.throttle_incidents: int = 0
        self._was_throttling: bool = False
        self.active_pid: int | None = None
        self._last_full_scan_time: float = 0.0

    def check_running_games(self) -> tuple[bool, str | None, str | None]:
        """
        Ultra-low overhead game detection optimized for zero in-game stutter.
        1. Fast PID check if game already active (<0.001 ms).
        2. Fast foreground window check on Windows (<0.005 ms).
        3. Rate-limited fallback full scan at most once every 10 seconds.
        """
        try:
            import psutil
            import time
            import os

            # 1. Fast PID verification if game already running
            if self.is_active and self.active_pid:
                if psutil.pid_exists(self.active_pid):
                    try:
                        p = psutil.Process(self.active_pid)
                        if p.is_running() and p.status() != getattr(psutil, "STATUS_ZOMBIE", "zombie"):
                            return True, self.current_game, self.current_process
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            # 2. Fast foreground window check on Windows (<0.005 ms, zero stutter)
            if os.name == "nt":
                try:
                    import ctypes
                    from ctypes import wintypes
                    user32 = ctypes.windll.user32
                    hwnd = user32.GetForegroundWindow()
                    if hwnd:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value > 0:
                            p = psutil.Process(pid.value)
                            pname = (p.name() or "").lower()
                            if pname in KNOWN_GAME_PROCESSES:
                                self.active_pid = pid.value
                                return True, KNOWN_GAME_PROCESSES[pname], pname
                except Exception:
                    pass

            # 3. Rate-limited process tree scan (only run every 10s if not found)
            now = time.time()
            if (now - self._last_full_scan_time) < 10.0:
                if self.is_active:
                    return True, self.current_game, self.current_process
                return False, None, None

            self._last_full_scan_time = now
            for proc in psutil.process_iter(attrs=["pid", "name"]):
                try:
                    pname = (proc.info.get("name") or "").lower()
                    if pname in KNOWN_GAME_PROCESSES:
                        self.active_pid = proc.info.get("pid")
                        return True, KNOWN_GAME_PROCESSES[pname], pname
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except ImportError:
            pass
        return False, None, None

    def poll_detection(self, current_metrics: dict | None = None) -> bool:
        """
        Evaluates system state to automatically engage or disengage Game Mode.
        Returns True if Game Mode is active after evaluation.
        """
        if self.manual_override is not None:
            desired_state = self.manual_override
            game_title = self.current_game or "Manual Game Mode"
            proc_name = self.current_process or "manual_override"
        else:
            game_found, detected_title, detected_proc = self.check_running_games()
            if game_found:
                desired_state = True
                game_title = detected_title
                proc_name = detected_proc
            else:
                desired_state = False
                game_title = None
                proc_name = None

        if desired_state and not self.is_active:
            self._start_session(game_title or "Gaming Session", proc_name or "unknown.exe")
        elif not desired_state and self.is_active:
            self._end_session()

        return self.is_active

    def toggle_manual_mode(self) -> tuple[bool, str]:
        """
        Manually toggles Game Mode on or off, overriding automatic detection.
        Returns: (is_now_active: bool, message: str)
        """
        if self.is_active:
            self.reset_manual_override()
            self._end_session()
            return False, "Game Mode deactivated manually. Automatic detection resumed."
        else:
            self.manual_override = True
            self._start_session("Custom Game Session", "manual_override.exe")
            return True, "Game Mode activated manually (Do Not Disturb enabled)."

    def reset_manual_override(self):
        """Clears manual override and returns to automatic process detection."""
        self.manual_override = None

    def sample_telemetry(self, metrics: dict):
        """
        Ingests real-time metrics during an active gaming session.
        Calculates thermal stress, detects throttling incidents, and accumulates statistics.
        """
        if not self.is_active:
            return

        cpu = metrics.get("cpu", {})
        gpu = metrics.get("gpu", {})

        cpu_temp = float(cpu.get("temperature", 0.0) or 0.0)
        gpu_temp = float(gpu.get("temperature", 0.0) or 0.0)
        cpu_pwr = float(cpu.get("power_watts", 0.0) or 0.0)
        gpu_pwr = float(gpu.get("power_watts", 0.0) or 0.0)
        cpu_usage = float(cpu.get("usage", 0.0) or 0.0)
        gpu_usage = float(gpu.get("usage", 0.0) or 0.0)

        # Detect throttling incidents (CPU >= 95°C or GPU >= 87°C on modern RTX/Intel chips).
        # Count rising edges only: one sustained thermal event is one incident,
        # not hundreds of per-sample hits.
        throttling = cpu_temp >= 95.0 or gpu_temp >= 87.0
        if throttling and not self._was_throttling:
            self.throttle_incidents += 1
        self._was_throttling = throttling

        self.samples.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "cpu_temp": cpu_temp,
            "gpu_temp": gpu_temp,
            "cpu_power": cpu_pwr,
            "gpu_power": gpu_pwr,
            "cpu_usage": cpu_usage,
            "gpu_usage": gpu_usage,
        })

    def _start_session(self, game_title: str, process_name: str):
        """Initializes state and hooks for a new gaming session."""
        self.is_active = True
        self.current_game = game_title
        self.current_process = process_name
        self.session_start_time = datetime.datetime.now(datetime.timezone.utc)
        self.samples.clear()
        self.throttle_incidents = 0
        self._was_throttling = False

        if self.alert_manager:
            self.alert_manager.set_game_mode(True)

        if self.db_manager:
            try:
                self.session_id = self.db_manager.start_gaming_session(
                    game_title=game_title,
                    process_name=process_name
                )
            except Exception as e:
                logger.warning(f"Failed to record game session start in db: {e}")

        logger.info(f"🎮 Game Mode activated for {game_title} ({process_name})")
        if self.on_game_start:
            try:
                self.on_game_start(game_title)
            except Exception:
                pass

    def _end_session(self) -> GamingSessionSummary | None:
        """Concludes active gaming session, persists aggregates, and triggers report."""
        if not self.is_active:
            return None

        end_time = datetime.datetime.now(datetime.timezone.utc)
        start_time = self.session_start_time or end_time
        duration = int((end_time - start_time).total_seconds())

        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            duration_str = f"{hours}h {minutes}m {seconds}s"
        else:
            duration_str = f"{minutes}m {seconds}s"

        cpu_temps = [s["cpu_temp"] for s in self.samples if s["cpu_temp"] > 0]
        gpu_temps = [s["gpu_temp"] for s in self.samples if s["gpu_temp"] > 0]
        cpu_pwrs = [s["cpu_power"] for s in self.samples if s["cpu_power"] > 0]
        gpu_pwrs = [s["gpu_power"] for s in self.samples if s["gpu_power"] > 0]
        cpu_usages = [s["cpu_usage"] for s in self.samples]
        gpu_usages = [s["gpu_usage"] for s in self.samples]

        avg_cpu_temp = round(sum(cpu_temps) / len(cpu_temps), 1) if cpu_temps else 0.0
        max_cpu_temp = round(max(cpu_temps), 1) if cpu_temps else 0.0
        avg_gpu_temp = round(sum(gpu_temps) / len(gpu_temps), 1) if gpu_temps else 0.0
        max_gpu_temp = round(max(gpu_temps), 1) if gpu_temps else 0.0

        avg_cpu_pwr = round(sum(cpu_pwrs) / len(cpu_pwrs), 1) if cpu_pwrs else 0.0
        max_cpu_pwr = round(max(cpu_pwrs), 1) if cpu_pwrs else 0.0
        avg_gpu_pwr = round(sum(gpu_pwrs) / len(gpu_pwrs), 1) if gpu_pwrs else 0.0
        max_gpu_pwr = round(max(gpu_pwrs), 1) if gpu_pwrs else 0.0

        avg_cpu_usage = round(sum(cpu_usages) / len(cpu_usages), 1) if cpu_usages else 0.0
        max_cpu_usage = round(max(cpu_usages), 1) if cpu_usages else 0.0
        avg_gpu_usage = round(sum(gpu_usages) / len(gpu_usages), 1) if gpu_usages else 0.0
        max_gpu_usage = round(max(gpu_usages), 1) if gpu_usages else 0.0

        thermal_headroom = round(max(0.0, 90.0 - max_gpu_temp), 1) if max_gpu_temp > 0 else 25.0

        health_impact = 0.0
        if self.throttle_incidents > 0:
            health_impact = min(15.0, 5.0 + self.throttle_incidents * 2.0)
        elif max_gpu_temp > 83.0 or max_cpu_temp > 90.0:
            health_impact = 4.0

        summary = GamingSessionSummary(
            session_id=self.session_id,
            game_title=self.current_game or "Game Session",
            process_name=self.current_process or "unknown.exe",
            start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
            duration_seconds=duration,
            duration_formatted=duration_str,
            avg_cpu_temp=avg_cpu_temp,
            max_cpu_temp=max_cpu_temp,
            avg_gpu_temp=avg_gpu_temp,
            max_gpu_temp=max_gpu_temp,
            avg_cpu_power_watts=avg_cpu_pwr,
            max_cpu_power_watts=max_cpu_pwr,
            avg_gpu_power_watts=avg_gpu_pwr,
            max_gpu_power_watts=max_gpu_pwr,
            avg_cpu_usage=avg_cpu_usage,
            max_cpu_usage=max_cpu_usage,
            avg_gpu_usage=avg_gpu_usage,
            max_gpu_usage=max_gpu_usage,
            throttle_incidents=self.throttle_incidents,
            thermal_headroom_c=thermal_headroom,
            health_score_impact=health_impact,
        )

        if self.db_manager and self.session_id:
            try:
                self.db_manager.end_gaming_session(
                    session_id=self.session_id,
                    stats={
                        "duration_seconds": duration,
                        "avg_cpu_temp": avg_cpu_temp,
                        "max_cpu_temp": max_cpu_temp,
                        "avg_gpu_temp": avg_gpu_temp,
                        "max_gpu_temp": max_gpu_temp,
                        "avg_gpu_usage": avg_gpu_usage,
                        "max_gpu_usage": max_gpu_usage,
                        "avg_cpu_usage": avg_cpu_usage,
                        "max_cpu_usage": max_cpu_usage,
                        "avg_gpu_power_watts": avg_gpu_pwr,
                        "max_gpu_power_watts": max_gpu_pwr,
                        "avg_cpu_power_watts": avg_cpu_pwr,
                        "max_cpu_power_watts": max_cpu_pwr,
                        "throttle_incidents": self.throttle_incidents,
                        "health_score_impact": health_impact,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to record game session end in db: {e}")

        if self.alert_manager:
            self.alert_manager.set_game_mode(False)

        self.is_active = False
        self.current_game = None
        self.current_process = None
        self.session_id = None
        self.samples.clear()

        logger.info(f"🏁 Game Mode ended. Duration: {duration_str}, Max GPU Temp: {max_gpu_temp}°C")
        if self.on_game_end:
            try:
                self.on_game_end(summary)
            except Exception:
                pass

        return summary
