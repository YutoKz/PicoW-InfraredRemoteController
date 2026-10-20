"""Connection failure diagnostics with a simulated WLAN and clock."""
import importlib.util
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class WiFiTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.status = 1
        self.wlan = Mock()
        self.wlan.isconnected.return_value = False
        self.wlan.status.side_effect = lambda: self.status
        self.wlan.disconnect.side_effect = lambda: setattr(self, "status", 0)
        self.wlan.connect.side_effect = lambda *_: setattr(self, "status", self.result_status)
        self.result_status = -2
        clock = SimpleNamespace(ticks_ms=lambda: self.now,
                                ticks_diff=lambda a, b: a-b, sleep_ms=self.sleep)
        network = SimpleNamespace(STA_IF=0, WLAN=lambda _: self.wlan,
                                  STAT_IDLE=0, STAT_CONNECTING=1,
                                  STAT_NO_AP_FOUND=-2, STAT_WRONG_PASSWORD=-3)
        spec = importlib.util.spec_from_file_location("wifi_test_module", "wifi.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"network": network, "time": clock}):
            spec.loader.exec_module(self.module)

    def sleep(self, ms):
        self.now += ms

    def test_failure_reason_survives_disconnect(self):
        for code, name in ((-2, "STAT_NO_AP_FOUND"), (-3, "STAT_WRONG_PASSWORD")):
            self.result_status = code
            with self.assertRaises(self.module.WiFiError) as caught:
                self.module.connect("private-ssid", "private-password")
            self.assertIn(name, str(caught.exception))
            self.assertIn(str(code), str(caught.exception))
            self.assertEqual(self.status, 0)
            self.assertNotIn("private", str(caught.exception))

    def test_timeout_retains_pending_status(self):
        self.result_status = 1
        with self.assertRaises(self.module.WiFiError) as caught:
            self.module.connect("private-ssid", "private-password", timeout_ms=400)
        self.assertIn("timeout", str(caught.exception))
        self.assertIn("STAT_CONNECTING", str(caught.exception))
        self.assertEqual(self.now, 400)

    def test_driver_error_does_not_echo_credentials(self):
        self.wlan.connect.side_effect = OSError("private-ssid private-password")
        with self.assertRaises(self.module.WiFiError) as caught:
            self.module.connect("private-ssid", "private-password")
        self.assertIn("connection request", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))

    def test_existing_connection_is_not_disrupted(self):
        self.wlan.isconnected.return_value = True
        self.assertIs(self.module.connect("ssid", "password"), self.wlan)
        self.wlan.disconnect.assert_not_called()
        self.wlan.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
