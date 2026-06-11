import unittest

from juryrig.dashboard import build_dashboard_html, build_dashboard_snapshot


class DashboardSnapshotTest(unittest.TestCase):
    def test_snapshot_catches_rigged_judge(self):
        snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["cases"], 3)
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


class DashboardHtmlTest(unittest.TestCase):
    def test_html_embeds_dashboard_data(self):
        html = build_dashboard_html()

        self.assertIn("window.__JURYRIG_DATA__", html)
        self.assertIn("Judge audit console", html)
        self.assertIn("Prompt injection", html)
        self.assertIn("Copy install", html)
        self.assertIn("juryrig-dashboard", html)


if __name__ == "__main__":
    unittest.main()
