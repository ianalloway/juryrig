import contextlib
import io
import socket
import unittest
from http.server import BaseHTTPRequestHandler

from juryrig.dashboard import (
    _bind_dashboard_server,
    build_dashboard_html,
    build_dashboard_report,
    build_dashboard_snapshot,
    build_gate_results,
    build_recommendations,
)


class _NoopHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(204)
        self.end_headers()


class DashboardSnapshotTest(unittest.TestCase):
    def test_snapshot_catches_rigged_judge(self):
        snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["cases"], 3)
        self.assertEqual(snapshot["thresholds"]["position"], 0.20)
        self.assertEqual(snapshot["thresholds"]["injection"], 0.15)
        self.assertEqual(snapshot["source"]["kind"], "demo")
        self.assertIn("injection", snapshot["recommendation_catalog"])
        self.assertEqual(snapshot["judges"]["fair"]["flagged"], [])
        self.assertIn("position", snapshot["judges"]["rigged"]["flagged"])
        self.assertIn("verbosity", snapshot["judges"]["rigged"]["flagged"])
        self.assertIn("injection", snapshot["judges"]["rigged"]["flagged"])

    def test_snapshot_has_panel_and_calibration(self):
        snapshot = build_dashboard_snapshot()

        self.assertIn("fair-judge", snapshot["panel"]["scores"])
        self.assertIn("rigged-judge", snapshot["panel"]["scores"])
        self.assertGreater(snapshot["panel"]["agreement"], 0.0)
        self.assertEqual(snapshot["panel"]["source"]["label"], "Demo panel slices")
        self.assertEqual(
            snapshot["calibration"]["source"]["label"],
            "Demo calibration data",
        )
        self.assertGreaterEqual(snapshot["calibration"]["fair"]["ece"], 0.0)
        self.assertGreaterEqual(snapshot["calibration"]["rigged"]["ece"], 0.0)

    def test_report_uses_threshold_overrides(self):
        snapshot = build_dashboard_snapshot()
        report = build_dashboard_report(
            snapshot,
            judge="rigged",
            thresholds={"injection": 0.8},
        )

        failed = {gate["key"] for gate in report["gates"] if gate["failed"]}
        self.assertEqual(failed, {"position", "verbosity"})
        self.assertEqual(report["thresholds"]["injection"], 0.8)
        self.assertEqual(
            [item["key"] for item in report["recommendations"]],
            ["position", "verbosity"],
        )

    def test_gate_helpers_return_ready_card_when_clean(self):
        snapshot = build_dashboard_snapshot()
        gates = build_gate_results(snapshot["judges"]["fair"])
        recommendations = build_recommendations(gates)

        self.assertFalse(any(gate["failed"] for gate in gates))
        self.assertEqual(recommendations[0]["key"], "ready")

    def test_positive_lift_gates_ignore_negative_deltas(self):
        report = {
            "position": {"flip_rate": 0.0},
            "verbosity": {"mean_delta": -0.40},
            "injection": {"max_delta": -0.60},
            "consistency": {"spread": 0.0},
        }
        gates = {gate["key"]: gate for gate in build_gate_results(report)}

        self.assertEqual(gates["verbosity"]["value"], -0.40)
        self.assertEqual(gates["verbosity"]["gate_value"], 0.0)
        self.assertFalse(gates["verbosity"]["failed"])
        self.assertEqual(gates["injection"]["value"], -0.60)
        self.assertEqual(gates["injection"]["gate_value"], 0.0)
        self.assertFalse(gates["injection"]["failed"])

    def test_positive_lift_gates_fail_on_positive_deltas(self):
        report = {
            "position": {"flip_rate": 0.0},
            "verbosity": {"mean_delta": 0.06},
            "injection": {"max_delta": 0.16},
            "consistency": {"spread": 0.0},
        }
        gates = {gate["key"]: gate for gate in build_gate_results(report)}

        self.assertTrue(gates["verbosity"]["failed"])
        self.assertTrue(gates["injection"]["failed"])

    def test_report_rejects_unknown_judge(self):
        with self.assertRaises(ValueError):
            build_dashboard_report(judge="missing")


class DashboardHtmlTest(unittest.TestCase):
    def test_html_embeds_dashboard_data(self):
        html = build_dashboard_html()

        self.assertIn("window.__JURYRIG_DATA__", html)
        self.assertIn("Judge audit console", html)
        self.assertIn("Prompt injection", html)
        self.assertIn("Copy install", html)
        self.assertIn("Export JSON", html)
        self.assertIn("Gate summary", html)
        self.assertIn("Thresholds", html)
        self.assertIn("Recommendations", html)
        self.assertIn("recommendation_catalog", html)
        self.assertIn("Demo calibration data", html)
        self.assertIn("Demo panel slices", html)
        self.assertIn("gate_value", html)
        self.assertIn("recommendations: recommendationsForGates(gates)", html)
        self.assertIn("juryrig-dashboard", html)


class DashboardServerTest(unittest.TestCase):
    def test_bind_dashboard_server_falls_back_when_port_is_busy(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        occupied_port = sock.getsockname()[1]
        server = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                server = _bind_dashboard_server(
                    "127.0.0.1",
                    occupied_port,
                    _NoopHandler,
                )
            self.assertNotEqual(server.server_address[1], occupied_port)
        finally:
            if server:
                server.server_close()
            sock.close()


if __name__ == "__main__":
    unittest.main()
