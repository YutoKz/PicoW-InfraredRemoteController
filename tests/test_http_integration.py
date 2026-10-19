"""Real TCP/HTTP round trip using the production handler and simulated IR."""
import json
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request

from http_server import Application
from presets import PresetStore


class HTTPIntegrationTests(unittest.TestCase):
    def test_control_session_over_tcp(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PresetStore(directory)
            store.save({"version": 1, "id": "off", "label": "停止", "carrier_hz": 38000,
                        "pulses_us": [9000, 4500, 560]})
            sent = []
            config = SimpleNamespace(API_TOKEN="test" * 16, IR_CARRIER_HZ=38000, MIN_SEND_INTERVAL_MS=1000)
            app = Application(config, store, SimpleNamespace(send=lambda p: sent.append(p["id"])),
                              SimpleNamespace(capture=lambda: [3500, 1750, 430]))
            server = socket.socket()
            server.bind(("127.0.0.1", 0))
            server.listen(2)
            server.settimeout(0.1)
            stopped = threading.Event()
            failures = []

            def serve():
                while not stopped.is_set():
                    try:
                        client, _ = server.accept()
                    except socket.timeout:
                        continue
                    try:
                        app.handle(client)
                    except Exception as error:
                        failures.append(error)
                    finally:
                        client.close()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base = "http://127.0.0.1:%d" % server.getsockname()[1]

            def call(path, data=None, auth=True):
                headers = {"Authorization": "Bearer " + config.API_TOKEN} if auth else {}
                if data is not None:
                    headers["Content-Type"] = "application/json"
                request = urllib.request.Request(base + path, headers=headers,
                                                  data=None if data is None else json.dumps(data).encode())
                try:
                    with opener.open(request, timeout=3) as response:
                        content = response.read()
                        return response.status, content if path == "/" else json.loads(content)
                except urllib.error.HTTPError as error:
                    with error:
                        return error.code, json.loads(error.read())

            try:
                self.assertEqual(call("/", auth=False)[0], 200)
                self.assertEqual(call("/api/presets", auth=False)[0], 401)
                self.assertEqual(call("/api/send", {"id": "off"}, auth=False)[0], 401)
                self.assertEqual(call("/api/send")[0], 405)
                self.assertEqual(call("/api/status")[1]["last_sent"], None)
                self.assertEqual(call("/api/send", {"id": "off"})[1]["sent"], "off")
                self.assertEqual(call("/api/send", {"id": "off"})[0], 429)
                self.assertEqual(call("/api/learn", {"id": "cool_26", "label": "冷房26℃"})[0], 200)
                self.assertEqual(len(call("/api/presets")[1]["presets"]), 2)
                self.assertEqual(call("/api/learn", {"id": "cool_26", "label": "冷房26℃"})[0], 409)
                self.assertEqual(call("/api/delete", {"id": "cool_26"})[0], 200)
                self.assertEqual(call("/api/status")[1]["appliance_state"], "unknown")
                self.assertEqual(sent, ["off"])
                self.assertEqual(failures, [])
            finally:
                stopped.set()
                thread.join(timeout=3)
                server.close()
