"""
ui/alert_manager.py - State-based hysteresis alert debouncing and notification dispatch.
Supports Game Mode Do-Not-Disturb (DND) suppression to prevent in-game popups.

Two complementary anti-spam layers:
  1. Hysteresis: a metric must fall `hysteresis_delta` below its warn threshold
     before it can return to NORMAL, so a fluttering sensor can't flap states.
  2. Time debounce: a repeat WARNING/CRITICAL firing for the same metric inside
     `debounce_seconds` is suppressed (the state still updates; only the
     notification is held back).
"""
import time
from collections.abc import Callable
from enum import Enum


class AlertState(Enum):
    NORMAL = 0
    WARNING = 1
    CRITICAL = 2


class AlertManager:
    def __init__(
        self,
        hysteresis_delta: float = 3.0,
        debounce_seconds: float = 60.0,
        notification_callback: Callable[[str, str, AlertState], None] | None = None,
        game_mode: bool = False,
    ):
        self.hysteresis_delta = hysteresis_delta
        self.debounce_seconds = debounce_seconds
        self.notification_callback = notification_callback
        self.game_mode: bool = game_mode
        self.allow_critical_in_game_mode: bool = True
        self._states: dict[str, AlertState] = {}
        self._last_fired: dict[str, float] = {}

    def set_notification_callback(self, callback: Callable[[str, str, AlertState], None] | None):
        self.notification_callback = callback

    def set_game_mode(self, enabled: bool):
        self.game_mode = enabled

    def is_game_mode(self) -> bool:
        return self.game_mode

    def evaluate(
        self,
        metric_key: str,
        current_value: float,
        warn_threshold: float,
        crit_threshold: float,
    ) -> tuple[bool, AlertState, str | None]:
        val = float(current_value if current_value is not None else 0.0)
        prev_state = self._states.get(metric_key, AlertState.NORMAL)
        new_state = prev_state
        message = None
        unit = "°C" if "temp" in metric_key.lower() else "%"

        if val >= crit_threshold:
            new_state = AlertState.CRITICAL
        elif val >= warn_threshold:
            if prev_state != AlertState.CRITICAL:
                new_state = AlertState.WARNING
        elif val < (warn_threshold - self.hysteresis_delta):
            new_state = AlertState.NORMAL
        elif prev_state == AlertState.CRITICAL and val < (crit_threshold - self.hysteresis_delta):
            new_state = AlertState.WARNING

        if new_state != prev_state:
            self._states[metric_key] = new_state

            # Time-based debounce: suppress repeat WARNING/CRITICAL chatter for
            # a metric that re-fires inside the cooldown window.  Recovery
            # ("Normalized") messages always go through.
            if new_state in (AlertState.WARNING, AlertState.CRITICAL):
                now = time.monotonic()
                last = self._last_fired.get(metric_key, 0.0)
                if now - last < self.debounce_seconds:
                    return False, new_state, None
                self._last_fired[metric_key] = now

            if new_state == AlertState.CRITICAL:
                message = f"{metric_key.upper()} Critical: {val:.1f}{unit}"
            elif new_state == AlertState.WARNING:
                message = f"{metric_key.upper()} High: {val:.1f}{unit}"
            elif new_state == AlertState.NORMAL:
                message = f"{metric_key.upper()} Normalized: {val:.1f}{unit}"

            if new_state == AlertState.CRITICAL and self.notification_callback:
                if not self.game_mode or self.allow_critical_in_game_mode:
                    try:
                        self.notification_callback(metric_key, message, new_state)
                    except Exception:
                        pass

            return True, new_state, message

        return False, prev_state, None
