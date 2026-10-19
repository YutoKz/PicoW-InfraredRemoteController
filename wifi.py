"""DHCP Wi-Fi with a finite timeout; callers implement retry/backoff."""
import network
import time


def connect(ssid=None, password=None, timeout_ms=20000):
    if ssid is None:
        import config
        ssid, password = config.WIFI_SSID, config.WIFI_PASSWORD
        timeout_ms = config.WIFI_TIMEOUT_MS
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan
    wlan.disconnect()
    wlan.connect(ssid, password)
    start = time.ticks_ms()
    while not wlan.isconnected():
        if wlan.status() < 0 or time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
            wlan.disconnect()
            raise OSError("Wi-Fi connection failed or timed out")
        time.sleep_ms(200)
    return wlan
