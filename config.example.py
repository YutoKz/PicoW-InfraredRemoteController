# Copy to config.py. Never commit credentials.
WIFI_SSID = ""
WIFI_PASSWORD = ""
# Generate on your computer: python -c "import secrets; print(secrets.token_hex(32))"
API_TOKEN = ""
HTTP_PORT = 80
IR_SEND_PIN = 17       # GPIO number, physical pin 22. Active-high driver.
IR_RECEIVE_PIN = 26    # Physical pin 31. Active-low, 3.3 V demodulating receiver.
# Use None if no receiver is fitted (sending saved presets still works).
IR_STATE_MACHINE = 0
IR_CARRIER_HZ = 38000  # A demodulating receiver cannot measure carrier frequency.
CAPTURE_IDLE_MS = 120  # Must exceed every gap WITHIN one command.
CAPTURE_TIMEOUT_MS = 10000
WIFI_TIMEOUT_MS = 20000
MIN_SEND_INTERVAL_MS = 1000
PRESET_DIRECTORY = "codes"
