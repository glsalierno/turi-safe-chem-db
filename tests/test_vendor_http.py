import unittest
from unittest.mock import Mock, patch

import requests

from packages.doss_core import fisher, tci, vendor_http


def response(status):
    reply = requests.Response()
    reply.status_code = status
    reply._content = b"%PDF-fixture" if status == 200 else b"error"
    reply.headers["Content-Type"] = "application/pdf"
    return reply


class VendorHTTPTests(unittest.TestCase):
    def get(self):
        return vendor_http.get_vendor_response(
            "https://example.invalid/sds", vendor="fixture", headers={},
            throttle=Mock(), timeout=(5, 25),
        )

    def test_transient_errors_retry_then_succeed(self):
        with (
            patch.object(requests, "get", side_effect=[
                requests.ConnectionError("offline fixture"), response(503), response(200),
            ]) as get,
            patch.object(vendor_http.time, "sleep"),
        ):
            self.assertEqual(self.get(), (200, b"%PDF-fixture", "application/pdf"))
            self.assertEqual(get.call_count, 3)
            self.assertEqual(get.call_args.kwargs["timeout"], (5, 25))

    def test_denial_logs_and_does_not_retry(self):
        with (
            patch.object(requests, "get", return_value=response(403)) as get,
            self.assertLogs("doss", level="WARNING") as logs,
        ):
            self.assertEqual(self.get(), (403, b"error", ""))
            get.assert_called_once()
            self.assertIn("status=403", logs.output[0])

    def test_timeout_exhaustion_fails_closed(self):
        with (
            patch.object(requests, "get", side_effect=requests.Timeout("fixture")) as get,
            patch.object(vendor_http.time, "sleep"),
            self.assertLogs("doss", level="WARNING"),
        ):
            self.assertEqual(self.get(), (0, b"", ""))
            self.assertEqual(get.call_count, 3)

    def test_vendor_clients_supply_explicit_connect_and_read_timeouts(self):
        for client, read_timeout in ((fisher, 30), (tci, 25)):
            with patch.object(client, "get_vendor_response") as get:
                client._http_get("https://example.invalid/sds")
                self.assertEqual(get.call_args.kwargs["timeout"], (5.0, read_timeout))
