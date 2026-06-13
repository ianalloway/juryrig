import unittest

from juryrig.dashboard import (
    build_dashboard_html,
    build_dashboard_report,
    build_dashboard_snapshot,
    build_gate_results,
    build_recommendations,
)


class DashboardSnapshotTest(unittest.TestCase):
    def test_snapshot_catches_rigged_judge(self):
        snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["cases"], 3)
        self.assertEqual(snapshot["thresholds"]["position"], 0.20)
        self.assertEqual(snapshot["thresholds"]["injection"], 0.15)
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
        self.assertIn("juryrig-dashboard", html)


if __name__ == "__main__":
    unittest.main()
