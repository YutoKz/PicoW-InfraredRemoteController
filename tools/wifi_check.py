"""Run on Pico: mpremote connect COM3 run tools/wifi_check.py. No IR output."""
import network
import config
from wifi import connect, WiFiError, status_name, error_code


def main():
    print("Wi-Fi diagnostics: SSID, password, API token and BSSIDs are not printed.")
    print("SSID configured:", bool(config.WIFI_SSID))
    print("Password configured:", bool(config.WIFI_PASSWORD))
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.disconnect()
    except OSError as error:
        print("Interface activation failed: errno=", error_code(error))
        return
    try:
        target = config.WIFI_SSID.encode("utf-8")
        matches = [ap for ap in wlan.scan() if ap[0] == target]
        print("Configured SSID visible:", bool(matches))
        for ap in matches:
            print("Target AP: channel=%s RSSI=%s security=%s" % (ap[2], ap[3], ap[4]))
        if not matches:
            print("Check 2.4 GHz, exact SSID and signal. A hidden SSID may not appear.")
    except OSError as error:
        print("Scan failed: errno=", error_code(error))
    print("Connecting with config.py; timeout_ms=", config.WIFI_TIMEOUT_MS)
    try:
        wlan = connect(config.WIFI_SSID, config.WIFI_PASSWORD, config.WIFI_TIMEOUT_MS)
    except WiFiError as error:
        print(error)
        return
    print("Connected:", wlan.isconnected())
    print("Status:", wlan.status(), status_name(wlan.status()))
    print("IPv4:", wlan.ifconfig()[0])
    print("No IR was sent. Reset the Pico to start the web server.")


main()
