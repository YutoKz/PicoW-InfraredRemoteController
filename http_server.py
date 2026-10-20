"""Small bounded HTTP/1.x server for a trusted LAN/VPN, compatible with CPython."""
import json
import time

MAX_HEADERS = 4096
MAX_BODY = 2048
REQUEST_TIMEOUT_MS = 5000


def ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def ticks_diff(now, then):
    return time.ticks_diff(now, then) if hasattr(time, "ticks_diff") else now - then


class HTTPError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def read_request(sock):
    start = ticks_ms()
    data = b""

    def receive(count):
        remaining = REQUEST_TIMEOUT_MS - ticks_diff(ticks_ms(), start)
        if remaining <= 0:
            raise HTTPError(408, "Request timed out")
        sock.settimeout(remaining / 1000)
        chunk = sock.recv(count)
        if not chunk:
            raise HTTPError(400, "Incomplete request")
        return chunk

    while b"\r\n\r\n" not in data:
        if len(data) >= MAX_HEADERS:
            raise HTTPError(413, "Headers too large")
        data += receive(min(256, MAX_HEADERS - len(data)))
    header_bytes, body = data.split(b"\r\n\r\n", 1)
    try:
        lines = header_bytes.decode("ascii").split("\r\n")
        method, path, version = lines[0].split(" ")
        if version not in ("HTTP/1.0", "HTTP/1.1") or not path.startswith("/"):
            raise ValueError()
        headers = {}
        for line in lines[1:]:
            if line.startswith((" ", "\t")) or ":" not in line:
                raise ValueError()
            key, value = line.split(":", 1)
            if not key or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in key):
                raise ValueError()
            key = key.lower()
            if key in headers:
                raise ValueError()
            headers[key] = value.strip()
        if "transfer-encoding" in headers:
            raise ValueError()
        raw_length = headers.get("content-length", "0")
        if not raw_length or not all("0" <= c <= "9" for c in raw_length):
            raise ValueError()
        length = int(raw_length)
    except (ValueError, UnicodeError):
        raise HTTPError(400, "Malformed HTTP request")
    if length > MAX_BODY:
        raise HTTPError(413, "Body too large")
    if method == "POST" and "content-length" not in headers:
        raise HTTPError(411, "Content-Length required")
    while len(body) < length:
        body += receive(length - len(body))
    return method, path, headers, body[:length]


def authorized(headers, token):
    expected = "Bearer " + token
    received = headers.get("authorization", "")
    if len(received) != len(expected):
        return False
    difference = 0
    for i in range(len(expected)):
        difference |= ord(received[i]) ^ ord(expected[i])
    return difference == 0


def send_bytes(sock, data):
    view = memoryview(data)
    sent = 0
    while sent < len(data):
        count = sock.send(view[sent:])
        if not count:
            raise OSError("Connection closed during response")
        sent += count


def response(sock, status, payload, content_type="application/json; charset=utf-8"):
    if isinstance(payload, dict):
        payload = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload = payload.encode("utf-8")
    reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
              405: "Method Not Allowed", 408: "Request Timeout", 409: "Conflict",
              411: "Length Required", 413: "Payload Too Large", 415: "Unsupported Media Type",
              429: "Too Many Requests", 500: "Internal Server Error", 503: "Service Unavailable"}.get(status, "Error")
    headers = ("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
               "Connection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
               "X-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\n"
               "Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; "
               "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'\r\n\r\n")
    sock.settimeout(5)
    send_bytes(sock, (headers % (status, reason, content_type, len(payload))).encode("ascii"))
    send_bytes(sock, payload)


class Application:
    def __init__(self, config, store, transmitter, receiver=None):
        self.config = config
        self.store = store
        self.transmitter = transmitter
        self.receiver = receiver
        self.last_sent = None
        self.last_sent_at = None

    def dispatch(self, method, path, headers, body):
        if path == "/" and method == "GET":
            with open("index.html", "r") as file:
                return 200, file.read(), "text/html; charset=utf-8"
        if not path.startswith("/api/"):
            raise HTTPError(404, "Not found")
        if not authorized(headers, self.config.API_TOKEN):
            raise HTTPError(401, "Invalid access key")
        json_type = "application/json; charset=utf-8"
        if path == "/api/presets" and method == "GET":
            return 200, {"presets": self.store.summaries()}, json_type
        if path == "/api/status" and method == "GET":
            return 200, {"can_learn": self.receiver is not None,
                         "carrier_hz": self.config.IR_CARRIER_HZ,
                         "last_sent": self.last_sent,
                         "appliance_state": "unknown"}, json_type
        if path not in ("/api/send", "/api/learn", "/api/delete"):
            raise HTTPError(404, "Not found")
        if method != "POST":
            raise HTTPError(405, "Use POST")
        if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPError(415, "Use application/json")
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise HTTPError(400, "Invalid JSON")
        if not isinstance(data, dict):
            raise HTTPError(400, "Expected a JSON object")
        from presets import validate_id, validate_label, validate_carrier, validate_preset
        preset_id = validate_id(data.get("id"))
        if path == "/api/send":
            preset = self.store.load(preset_id)
            now = ticks_ms()
            if self.last_sent_at is not None and ticks_diff(now, self.last_sent_at) < self.config.MIN_SEND_INTERVAL_MS:
                raise HTTPError(429, "Wait before sending another command")
            self.last_sent_at = now
            self.transmitter.send(preset)
            self.last_sent = preset_id
            return 200, {"sent": preset_id, "appliance_state": "unknown"}, json_type
        if path == "/api/delete":
            self.store.delete(preset_id)
            return 200, {"deleted": preset_id}, json_type
        if self.receiver is None:
            raise HTTPError(503, "IR receiver is not configured")
        # Do not replace an existing recording implicitly.
        if preset_id in self.store.ids():
            raise HTTPError(409, "ID already exists; use a new ID or delete it first")
        label = validate_label(data.get("label"))
        carrier = validate_carrier(data.get("carrier_hz", self.config.IR_CARRIER_HZ))
        from presets import MAX_PRESETS
        if len(self.store.ids()) >= MAX_PRESETS:
            raise HTTPError(409, "Maximum 32 presets")
        preset = validate_preset({"version": 1, "id": preset_id, "label": label,
                                  "carrier_hz": carrier, "pulses_us": self.receiver.capture()})
        self.store.save(preset)
        return 200, {"saved": preset_id, "pulse_count": len(preset["pulses_us"])}, json_type

    def handle(self, sock):
        try:
            result = self.dispatch(*read_request(sock))
        except HTTPError as error:
            result = error.status, {"error": str(error)}, "application/json"
        except KeyError:
            result = 404, {"error": "Preset not found"}, "application/json"
        except ValueError as error:
            result = 400, {"error": str(error)}, "application/json"
        except OSError:
            result = 503, {"error": "I/O failed; transmission may be incomplete. Check device before retrying."}, "application/json"
        except Exception as error:
            print("Request failed:", type(error).__name__)
            result = 500, {"error": "Internal error"}, "application/json"
        try:
            response(sock, *result)
        except OSError:
            pass
