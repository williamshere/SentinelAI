from types import SimpleNamespace
from unittest.mock import patch

import sensors.storage_health as storage_health


class FakeStartupInfo:
    dwFlags = 0
    wShowWindow = 0


def test_unavailable_storage_fallback_keeps_health_unknown():
    result = storage_health._fallback()

    assert result["available"] is False
    assert result["health_percent"] is None
    assert result["wear_percent"] is None
    assert result["tbw_terabytes"] is None
    assert result["read_errors"] is None


def test_missing_wear_field_does_not_become_zero_wear():
    storage_health._cached_result = None
    completed = SimpleNamespace(returncode=0, stdout='{"Model":"Example drive"}')
    with (
        patch.object(storage_health.os, "name", "nt"),
        patch.object(storage_health.subprocess, "STARTUPINFO", FakeStartupInfo, create=True),
        patch.object(storage_health.subprocess, "STARTF_USESHOWWINDOW", 1, create=True),
        patch.object(storage_health.subprocess, "run", return_value=completed),
    ):
        result = storage_health.get_storage_health(force_refresh=True)

    assert result["available"] is True
    assert result["wear_percent"] is None
    assert result["health_percent"] is None
