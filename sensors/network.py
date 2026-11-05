import time

try:
    import psutil
except ImportError:
    psutil = None

_last_net_io = None
_last_net_time = 0.0

def get_network_info() -> dict:
    global _last_net_io, _last_net_time
    now = time.time()

    try:
        if psutil is None:
            raise RuntimeError("psutil is not installed")

        net_io = psutil.net_io_counters()

        if _last_net_io is None:
            _last_net_io = net_io
            _last_net_time = now
            return {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "upload_speed_bps": 0.0,
                "download_speed_bps": 0.0,
                "available": True,
            }

        dt = now - _last_net_time
        if dt > 0:
            up_speed = (net_io.bytes_sent - _last_net_io.bytes_sent) / dt
            down_speed = (net_io.bytes_recv - _last_net_io.bytes_recv) / dt
        else:
            up_speed = 0.0
            down_speed = 0.0

        _last_net_io = net_io
        _last_net_time = now

        return {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "upload_speed_bps": up_speed,
            "download_speed_bps": down_speed,
            "available": True,
        }

    except Exception:
        return {
            "bytes_sent": 0,
            "bytes_recv": 0,
            "upload_speed_bps": 0.0,
            "download_speed_bps": 0.0,
            "available": False,
        }
