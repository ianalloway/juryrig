import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from juryrig import DEFAULT_THRESHOLDS
from juryrig.cli import load_cases, main

CASE_FILE = {
    "rubric": "Answer must mention photosynthesis chlorophyll sunlight energy",
    "cases": [
        {
            "prompt": "How do plants make food?",
            "good": "Plants use photosynthesis: chlorophyll captures sunlight energy.",
            "weak": "Plants eat soil.",
        }
    ],
}


class CliHarness(unittest.TestCase):
    def run_cli(self, payload, *args):
        """Write `payload` to a temp case file and run the CLI over it."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(
                payload if isinstance(payload, str) else json.dumps(payload)
            )
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(path), *args])
            return code, out.getvalue(), err.getvalue()


class ExitCodeTest(CliHarness):
    def test_clean_judge_exits_zero(self):
        code, out, _ = self.run_cli(CASE_FILE)

        self.assertEqual(code, 0)
        self.assertIn("PASSED", out)

    def test_json_output_is_parseable(self):
        code, out, _ = self.run_cli(CASE_FILE, "--json")

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertFalse(payload["flagged"])
        self.assertEqual(payload["failures"], [])
        self.assertIn("flip_rate", payload["audits"]["position"])
        self.assertTrue(payload["audits"]["position"]["flagged"] is False)

    def test_bad_case_file_exits_two(self):
        for payload in (
            "{not json",
            {"cases": []},
            {"rubric": "r", "cases": []},
            {"rubric": "r", "cases": [{"prompt": "p", "good": "g"}]},
            {"rubric": "   ", "cases": [{"prompt": "p", "good": "g", "weak": "w"}]},
        ):
            with self.subTest(payload=payload):
                code, _, err = self.run_cli(payload)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("juryrig:"))

    def test_flagged_judge_exits_one(self):
        # Both responses miss every rubric keyword, so they tie; compare()
        # breaks the tie toward slot A, which is exactly position bias.
        tied = {
            "rubric": CASE_FILE["rubric"],
            "cases": [
                {
                    "prompt": "How do plants make food?",
                    "good": "no relevant terms here",
                    "weak": "also nothing relevant",
                }
            ],
        }
        code, out, _ = self.run_cli(tied)

        self.assertEqual(code, 1)
        self.assertIn("FLAGGED by: position", out)

    def test_missing_file_exits_two(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["/nonexistent/cases.json"])

        self.assertEqual(code, 2)
        self.assertIn("juryrig:", err.getvalue())

    def test_rejects_non_positive_runs(self):
        code, _, err = self.run_cli(CASE_FILE, "--runs", "0")

        self.assertEqual(code, 2)
        self.assertIn("--runs", err)


class ThresholdsFromCaseFileTest(CliHarness):
    def test_loosened_threshold_turns_a_failure_into_a_pass(self):
        # Identical-scoring responses make compare() break the tie toward
        # slot A, which trips the position audit at the default tolerance.
        tied = {
            "rubric": CASE_FILE["rubric"],
            "cases": [{"prompt": "p", "good": "nothing", "weak": "also nothing"}],
        }
        flagged_code, _, _ = self.run_cli(tied)
        passed_code, out, _ = self.run_cli(
            {**tied, "thresholds": {"position_flip_rate": 1.0,
                                    "position_slot_skew": 0.5}}
        )

        self.assertEqual(flagged_code, 1)
        self.assertEqual(passed_code, 0)
        self.assertIn("PASSED", out)

    def test_unknown_threshold_key_is_rejected(self):
        code, _, err = self.run_cli(
            {**CASE_FILE, "thresholds": {"positon_flip_rate": 0.9}}  # typo
        )

        self.assertEqual(code, 2)
        self.assertIn("unknown threshold", err)
        self.assertIn("positon_flip_rate", err)

    def test_non_numeric_and_negative_thresholds_rejected(self):
        for overrides in ({"position_flip_rate": "high"}, {"position_flip_rate": -1}):
            with self.subTest(overrides=overrides):
                code, _, err = self.run_cli({**CASE_FILE, "thresholds": overrides})
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("juryrig:"))

    def test_json_output_reports_the_thresholds_used(self):
        _, out, _ = self.run_cli(
            {**CASE_FILE, "thresholds": {"verbosity_mean_delta": 0.42}}, "--json"
        )

        payload = json.loads(out)
        applied = payload["audits"]["verbosity"]["thresholds"]
        self.assertEqual(applied["verbosity_mean_delta"], 0.42)


class LoadCasesTest(unittest.TestCase):
    def test_reads_rubric_and_triples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(CASE_FILE))
            rubric, cases, thresholds = load_cases(path)

        self.assertEqual(rubric, CASE_FILE["rubric"])
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(cases[0]), 3)
        self.assertEqual(thresholds, DEFAULT_THRESHOLDS)


if __name__ == "__main__":
    unittest.main()
