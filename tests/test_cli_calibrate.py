"""`juryrig calibrate` — Brier, ECE and a reliability table from labels."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from juryrig.cli import format_reliability, load_labelled_scores, main

# Deliberately overconfident at the top end: four 0.8+ scores, half right.
MISCALIBRATED = {
    "scores": [0.95, 0.9, 0.85, 0.8, 0.3, 0.2, 0.15, 0.1],
    "labels": [1, 1, 0, 0, 0, 1, 0, 0],
    "bins": 5,
}
# 0.5 confidence, right half the time.
WELL_CALIBRATED = {"scores": [0.5] * 4, "labels": [1, 0, 1, 0], "bins": 2}


class Harness(unittest.TestCase):
    def run_cli(self, payload, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            path.write_text(
                payload if isinstance(payload, str) else json.dumps(payload)
            )
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["calibrate", str(path), *args])
            return code, out.getvalue(), err.getvalue()


class ExitCodeTest(Harness):
    def test_miscalibrated_judge_fails(self):
        code, out, _ = self.run_cli(MISCALIBRATED)

        self.assertEqual(code, 1)
        self.assertIn("FLAGGED", out)

    def test_well_calibrated_judge_passes(self):
        code, out, _ = self.run_cli(WELL_CALIBRATED)

        self.assertEqual(code, 0)
        self.assertIn("PASSED", out)

    def test_threshold_is_adjustable(self):
        code, _, _ = self.run_cli(MISCALIBRATED, "--max-ece", "0.9")

        self.assertEqual(code, 0)

    def test_json_output_is_parseable(self):
        code, out, _ = self.run_cli(MISCALIBRATED, "--json")

        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["pairs"], 8)
        self.assertTrue(payload["flagged"])
        self.assertGreater(payload["expected_calibration_error"], 0.1)
        self.assertIn("brier_score", payload)
        # Every bucket reports its own gap, which is where the story is.
        self.assertTrue(all("gap" in b for b in payload["reliability"]))

    def test_bins_can_be_overridden(self):
        _, out, _ = self.run_cli(MISCALIBRATED, "--json", "--bins", "2")

        self.assertEqual(json.loads(out)["bins"], 2)


class BadInputTest(Harness):
    def test_rejects_malformed_files(self):
        for payload in (
            "{not json",
            {},
            {"scores": [], "labels": []},
            {"scores": [0.5]},                        # no labels
            {"scores": [0.5], "labels": [1, 0]},      # length mismatch
            {"scores": [1.5], "labels": [1]},         # out of range
            {"scores": [0.5], "labels": [2]},         # not a 0/1 label
            {"scores": ["high"], "labels": [1]},      # not numeric
            {"scores": [0.5], "labels": [1], "bins": 0},
            {"cases": [{"score": 0.5}]},              # case missing label
        ):
            with self.subTest(payload=payload):
                code, _, err = self.run_cli(payload)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("juryrig:"), err)

    def test_rejects_negative_max_ece(self):
        code, _, err = self.run_cli(WELL_CALIBRATED, "--max-ece", "-1")

        self.assertEqual(code, 2)
        self.assertIn("--max-ece", err)

    def test_missing_file_exits_two(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["calibrate", "/nonexistent/labels.json"])

        self.assertEqual(code, 2)
        self.assertIn("juryrig:", err.getvalue())


class LoaderTest(unittest.TestCase):
    def read(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            path.write_text(json.dumps(payload))
            return load_labelled_scores(path)

    def test_reads_parallel_lists(self):
        scores, labels, bins = self.read(MISCALIBRATED)

        self.assertEqual(len(scores), 8)
        self.assertEqual(len(labels), 8)
        self.assertEqual(bins, 5)

    def test_accepts_per_case_objects(self):
        scores, labels, bins = self.read(
            {"cases": [{"score": 0.9, "label": 1}, {"score": 0.2, "label": 0}]}
        )

        self.assertEqual(scores, [0.9, 0.2])
        self.assertEqual(labels, [1, 0])
        self.assertEqual(bins, 10)   # default

    def test_booleans_are_not_accepted_as_scores(self):
        # bool is an int subclass; True would silently become 1.0.
        with self.assertRaises(ValueError):
            self.read({"scores": [True], "labels": [1]})


class FormatTest(unittest.TestCase):
    def table(self):
        from juryrig import reliability_table

        return reliability_table(
            MISCALIBRATED["scores"], MISCALIBRATED["labels"], 5
        )

    def test_ascii_includes_a_gap_column(self):
        rendered = format_reliability(self.table())

        self.assertIn("gap", rendered)
        self.assertIn("accuracy", rendered)

    def test_markdown_is_a_pipe_table(self):
        rendered = format_reliability(self.table(), "markdown")

        self.assertTrue(rendered.startswith("| bucket"))
        self.assertIn("|---", rendered)


if __name__ == "__main__":
    unittest.main()
