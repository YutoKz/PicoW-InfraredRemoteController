"""Validate local configuration before opening the control server."""
GPIO_PINS = tuple(range(23)) + (26, 27, 28)


def validate(config):
    for name in ("WIFI_SSID", "WIFI_PASSWORD", "API_TOKEN"):
        if not isinstance(getattr(config, name, None), str):
            raise ValueError(name + " must be a string in config.py")
    if not config.WIFI_SSID.strip():
        raise ValueError("Set WIFI_SSID in config.py")
    token = config.API_TOKEN
    if len(token) < 32 or len(token) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("API_TOKEN must be 32-128 printable ASCII characters")
    if config.IR_SEND_PIN not in GPIO_PINS:
        raise ValueError("IR_SEND_PIN is not an exposed Pico W GPIO")
    if config.IR_RECEIVE_PIN is not None and (
        config.IR_RECEIVE_PIN not in GPIO_PINS or config.IR_RECEIVE_PIN == config.IR_SEND_PIN
    ):
        raise ValueError("IR_RECEIVE_PIN must be a different exposed GPIO or None")
    for name, low, high in (
        ("HTTP_PORT", 1, 65535), ("IR_STATE_MACHINE", 0, 7),
        ("IR_CARRIER_HZ", 30000, 60000), ("CAPTURE_IDLE_MS", 20, 500),
        ("CAPTURE_TIMEOUT_MS", 1000, 30000), ("WIFI_TIMEOUT_MS", 1000, 60000),
        ("MIN_SEND_INTERVAL_MS", 500, 60000),
    ):
        value = getattr(config, name, None)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid config.py setting: " + name)
    if not isinstance(config.PRESET_DIRECTORY, str) or not config.PRESET_DIRECTORY:
        raise ValueError("Set PRESET_DIRECTORY in config.py")
    return config
