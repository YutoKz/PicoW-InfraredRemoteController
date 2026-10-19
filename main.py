"""Boot entry point. No transmission on boot, reconnect, or import."""
import gc
import socket
import time


def run():
    import config
    from settings import validate
    from presets import PresetStore
    from ir_tx import IRTransmitter
    from http_server import Application
    from wifi import connect
    validate(config)
    receiver = None
    if config.IR_RECEIVE_PIN is not None:
        from read import IRReceiver
        receiver = IRReceiver(config.IR_RECEIVE_PIN, config.CAPTURE_IDLE_MS, config.CAPTURE_TIMEOUT_MS)
    app = Application(config, PresetStore(config.PRESET_DIRECTORY),
                      IRTransmitter(config.IR_SEND_PIN, config.IR_STATE_MACHINE), receiver)
    retry_seconds = 1
    while True:
        server = None
        try:
            wlan = connect(config.WIFI_SSID, config.WIFI_PASSWORD, config.WIFI_TIMEOUT_MS)
            server = socket.socket()
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", config.HTTP_PORT))
            server.listen(2)
            server.settimeout(1)
            print("Open http://%s:%d on your LAN/VPN" % (wlan.ifconfig()[0], config.HTTP_PORT))
            retry_seconds = 1
            while wlan.isconnected():
                try:
                    client, _ = server.accept()
                except OSError as error:
                    # MicroPython ports may use ETIMEDOUT or EAGAIN for a timeout.
                    if error.args and error.args[0] in (11, 110, 116):
                        continue
                    raise
                try:
                    app.handle(client)
                finally:
                    client.close()
                    gc.collect()
        except OSError:
            print("Network unavailable; retrying in", retry_seconds, "seconds")
        finally:
            if server is not None:
                server.close()
        time.sleep(retry_seconds)
        retry_seconds = min(retry_seconds * 2, 30)


if __name__ == "__main__":
    try:
        run()
    except (ImportError, ValueError) as error:
        print("Setup required:", error)
        print("Copy config.example.py to config.py and upload all runtime files. See README.md.")
