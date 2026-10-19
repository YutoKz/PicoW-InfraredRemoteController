import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from http_server import Application, HTTPError, read_request, response
from presets import PresetStore, validate_preset, MAX_PULSES, MAX_PRESETS
from settings import validate


def preset(preset_id="cool_26"):
    return {"version": 1, "id": preset_id, "label": "冷房26℃",
            "carrier_hz": 38000, "pulses_us": [9000, 4500, 560, 1690, 560]}


class Socket:
    def __init__(self, data=b"", fragment=100000, send_limit=100000):
        self.input = data
        self.output = b""
        self.fragment = fragment
        self.send_limit = send_limit

    def settimeout(self, value):
        self.timeout = value

    def recv(self, size):
        count = min(size, self.fragment)
        result, self.input = self.input[:count], self.input[count:]
        return result

    def send(self, data):
        chunk = bytes(data[:self.send_limit])
        self.output += chunk
        return len(chunk)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = PresetStore(self.tmp.name)

    def test_round_trip_and_atomic_replace(self):
        first = preset()
        self.store.save(first)
        second = preset()
        second["label"] = "冷房26℃・風量自動"
        self.store.save(second)
        self.assertEqual(self.store.load(first["id"]), second)
        self.assertNotIn("pulses_us", self.store.summaries()[0])
        self.assertEqual(os.listdir(self.tmp.name), ["cool_26.json"])

    def test_failed_replace_preserves_previous_recording(self):
        self.store.save(preset())
        changed = preset()
        changed["label"] = "変更"
        with patch("presets.os.rename", side_effect=OSError("flash failure")):
            with self.assertRaises(OSError):
                self.store.save(changed)
        self.assertEqual(self.store.load("cool_26"), preset())
        self.assertEqual(os.listdir(self.tmp.name), ["cool_26.json"])

    def test_unfinished_temporary_file_not_listed(self):
        Path(self.tmp.name, "cool_26.json.tmp").write_text("partial")
        self.assertEqual(self.store.ids(), [])

    def test_invalid_data_never_overwrites_existing(self):
        self.store.save(preset())
        invalid = preset()
        invalid["pulses_us"] = [1, 2, 3]
        with self.assertRaises(ValueError):
            self.store.save(invalid)
        self.assertEqual(self.store.load("cool_26"), preset())

    def test_traversal_and_mismatched_id(self):
        for value in ("../config", "/config", "", "COOL", "a/b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.load(value)
        Path(self.tmp.name, "wrong.json").write_text(json.dumps(preset()))
        with self.assertRaises(ValueError):
            self.store.load("wrong")

    def test_limits(self):
        for pulses in ([560, 560], [True, 560, 560], [560.0, 560, 560],
                       [500001, 560, 560], [500000] * 5, [560] * (MAX_PULSES + 2)):
            invalid = preset()
            invalid["pulses_us"] = pulses
            with self.subTest(pulses=pulses[:4]), self.assertRaises(ValueError):
                validate_preset(invalid)
        for index in range(MAX_PRESETS):
            self.store.save(preset("code_" + str(index)))
        with self.assertRaises(ValueError):
            self.store.save(preset("overflow"))
        self.store.delete("code_0")
        self.store.save(preset("new"))


class HTTPParsingTests(unittest.TestCase):
    def test_fragmented_headers_and_body(self):
        request = b'POST /api/send HTTP/1.1\r\nContent-Length: 16\r\n\r\n{"id":"cool_26"}'
        method, path, headers, body = read_request(Socket(request, fragment=1))
        self.assertEqual((method, path, body), ("POST", "/api/send", b'{"id":"cool_26"}'))

    def test_invalid_framing(self):
        for header in (
            b"Content-Length: -1", b"Content-Length: 999999", b"Content-Length: 3\r\nContent-Length: 3",
            b"Content-Length: 3\r\nTransfer-Encoding: chunked", b"Folded: a\r\n continuation",
            b"Content-Length : 0", b"Content-Length: +3", b"Content-Length: 0xff",
        ):
            with self.subTest(header=header), self.assertRaises(HTTPError):
                read_request(Socket(b"POST /api/send HTTP/1.1\r\n" + header + b"\r\n\r\n"))

    def test_truncated_body_and_missing_length(self):
        for request in (b"POST /api/send HTTP/1.1\r\n\r\n",
                        b"POST /api/send HTTP/1.1\r\nContent-Length: 5\r\n\r\na"):
            with self.assertRaises(HTTPError):
                read_request(Socket(request))

    def test_header_limit(self):
        with self.assertRaises(HTTPError) as error:
            read_request(Socket(b"GET / HTTP/1.1\r\nX-Long: " + b"x" * 5000))
        self.assertEqual(error.exception.status, 413)

    def test_whole_request_deadline(self):
        with patch("http_server.ticks_ms", side_effect=[0, 6000]):
            with self.assertRaises(HTTPError) as error:
                read_request(Socket(b"GET / HTTP/1.1\r\n\r\n"))
        self.assertEqual(error.exception.status, 408)

    def test_partial_response_writes_and_utf8_length(self):
        sock = Socket(send_limit=3)
        response(sock, 200, {"message": "冷房"})
        headers, body = sock.output.split(b"\r\n\r\n")
        self.assertIn(b"Content-Length: " + str(len(body)).encode(), headers)
        self.assertEqual(json.loads(body), {"message": "冷房"})
        self.assertIn(b"Cache-Control: no-store", headers)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = PresetStore(self.tmp.name)
        self.store.save(preset())
        self.sent = []
        self.config = SimpleNamespace(API_TOKEN="a" * 64, IR_CARRIER_HZ=38000, MIN_SEND_INTERVAL_MS=1000)
        self.app = Application(self.config, self.store, SimpleNamespace(send=self.sent.append))
        self.headers = {"authorization": "Bearer " + self.config.API_TOKEN, "content-type": "application/json"}

    def request(self, path, data, method="POST", headers=None):
        return self.app.dispatch(method, path, headers if headers is not None else self.headers,
                                 json.dumps(data).encode())

    def test_no_side_effects_on_start_or_status(self):
        self.request("/api/status", None, method="GET")
        self.request("/api/presets", None, method="GET")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.app.last_sent, None)

    def test_unauthorized_and_get_never_send(self):
        for headers in ({}, {"authorization": "Bearer wrong"}):
            with self.assertRaises(HTTPError) as error:
                self.request("/api/send", {"id": "cool_26"}, headers=headers)
            self.assertEqual(error.exception.status, 401)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/send", {"id": "cool_26"}, method="GET")
        self.assertEqual(error.exception.status, 405)
        self.assertEqual(self.sent, [])

    def test_missing_unknown_or_invalid_never_send(self):
        for data in ({}, {"id": "unknown"}, {"id": "../config"}, [], None):
            with self.subTest(data=data), self.assertRaises((ValueError, KeyError, HTTPError)):
                self.request("/api/send", data)
        self.assertEqual(self.sent, [])

    def test_requires_json_content_type(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/send", {"id": "cool_26"}, headers={"authorization": self.headers["authorization"]})
        self.assertEqual(error.exception.status, 415)

    def test_send_throttle_and_unknown_appliance_state(self):
        with patch("http_server.ticks_ms", return_value=100):
            status, result, _ = self.request("/api/send", {"id": "cool_26"})
            with self.assertRaises(HTTPError) as error:
                self.request("/api/send", {"id": "cool_26"})
        self.assertEqual(status, 200)
        self.assertEqual(result["appliance_state"], "unknown")
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(self.sent, [preset()])
        with patch("http_server.ticks_ms", return_value=1100):
            self.request("/api/send", {"id": "cool_26"})
        self.assertEqual(len(self.sent), 2)

    def test_failed_transmission_not_reported_as_success(self):
        self.app.transmitter = SimpleNamespace(send=lambda _: (_ for _ in ()).throw(OSError("failure")))
        body = b'{"id":"cool_26"}'
        wire = ("POST /api/send HTTP/1.1\r\nAuthorization: Bearer %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % (self.config.API_TOKEN, len(body))).encode() + body
        sock = Socket(wire, fragment=7)
        self.app.handle(sock)
        self.assertTrue(sock.output.startswith(b"HTTP/1.1 503"))
        self.assertIsNone(self.app.last_sent)

    def test_learning_preserves_long_multiframe_signal(self):
        pulses = [3500, 1750] + [430, 430] * 216 + [430, 40000, 3500, 1750, 430]
        self.app.receiver = SimpleNamespace(capture=lambda: pulses)
        result = self.request("/api/learn", {"id": "heat_22", "label": "暖房22℃"})
        self.assertEqual(result[0], 200)
        self.assertEqual(self.store.load("heat_22")["pulses_us"], pulses)
        self.assertEqual(self.sent, [])

    def test_duplicate_learning_does_not_capture_or_replace(self):
        self.app.receiver = SimpleNamespace(capture=lambda: self.fail("must not capture"))
        with self.assertRaises(HTTPError) as error:
            self.request("/api/learn", {"id": "cool_26", "label": "changed"})
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store.load("cool_26"), preset())

    def test_learning_timeout_or_invalid_waveform_not_saved(self):
        for capture in (lambda: [], lambda: (_ for _ in ()).throw(ValueError("timeout"))):
            self.app.receiver = SimpleNamespace(capture=capture)
            with self.assertRaises(ValueError):
                self.request("/api/learn", {"id": "off", "label": "停止"})
        self.assertEqual(self.store.ids(), ["cool_26"])

    def test_delete_requires_auth_and_does_not_transmit(self):
        self.request("/api/delete", {"id": "cool_26"})
        self.assertEqual(self.store.ids(), [])
        self.assertEqual(self.sent, [])


class ConfigurationTests(unittest.TestCase):
    def test_template_fails_closed_until_configured(self):
        import runpy
        config = SimpleNamespace(**runpy.run_path("config.example.py"))
        with self.assertRaises(ValueError):
            validate(config)
        config.WIFI_SSID = "test"
        config.API_TOKEN = "a" * 64
        validate(config)
        config.IR_RECEIVE_PIN = config.IR_SEND_PIN
        with self.assertRaises(ValueError):
            validate(config)


if __name__ == "__main__":
    unittest.main()
