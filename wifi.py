"""DHCP Wi-Fi with a finite timeout; callers implement retry/backoff."""
import network
import time


class WiFiError(OSError):
    """Credential-free connection diagnostics suitable for the serial log."""


def status_name(status):
    for name in ("STAT_IDLE", "STAT_CONNECTING", "STAT_WRONG_PASSWORD",
                 "STAT_NO_AP_FOUND", "STAT_CONNECT_FAIL", "STAT_GOT_IP"):
        if getattr(network, name, None) == status:
            return name
    return "UNKNOWN"


def error_code(error):
    # Never echo arbitrary driver exception text (it could contain credentials).
    return error.args[0] if error.args and type(error.args[0]) is int else "unknown"


def connect(ssid=None, password=None, timeout_ms=20000):
    if ssid is None:
        import config
        ssid, password = config.WIFI_SSID, config.WIFI_PASSWORD
        timeout_ms = config.WIFI_TIMEOUT_MS
    stage = "interface activation"
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if wlan.isconnected():
            return wlan
        stage = "connection request"
        wlan.disconnect()
        wlan.connect(ssid, password)
        start = time.ticks_ms()
        stage = "waiting for IP"
        while not wlan.isconnected():
            status = wlan.status()
            timed_out = time.ticks_diff(time.ticks_ms(), start) >= timeout_ms
            if status < 0 or timed_out:
                # Capture the reason before disconnect() resets driver status.
                message = "Wi-Fi %s: status=%s (%s)" % (
                    "timeout" if timed_out else "failed", status, status_name(status))
                try:
                    wlan.disconnect()
                except OSError:
                    pass
                raise WiFiError(message)
            time.sleep_ms(200)
        return wlan
    except WiFiError:
        raise
    except OSError as error:
        raise WiFiError("Wi-Fi %s failed: errno=%s" % (stage, error_code(error)))
