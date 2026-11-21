"""Rubric sensitivity: does rewording the rubric move the score?"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from juryrig import Judgment, MockJudge, Thresholds, rubric_sensitivity
from juryrig.cli import load_rubric_variants, main

CASES = [
    ("How do plants make food?", "photosynthesis chlorophyll sunlight energy"),
    ("Explain plant energy.", "sunlight energy chlorophyll"),
]
RUBRICS = [
    "Answer must mention photosynthesis chlorophyll sunlight energy",
    "The response should explain photosynthesis using chlorophyll and sunlight",
    "Must cover photosynthesis, chlorophyll, sunlight, energy",
]


class IndifferentJudge:
    """Ignores the rubric entirely — the control case."""

    name = "indifferent"

    def judge(self, *, prompt, response, rubric):
        return Judgment(score=0.7)


class RubricFollowingJudge:
    """Scores purely on rubric length — maximally wording-sensitive."""

    name = "wording"

    def judge(self, *, prompt, response, rubric):
        return Judgment(score=min(len(rubric) / 100.0, 1.0))


class ValidationTest(unittest.TestCase):
    def test_needs_two_wordings(self):
        with self.assertRaises(ValueError):
            rubric_sensitivity(MockJudge(), CASES, [RUBRICS[0]])

    def test_needs_a_case(self):
        with self.assertRaises(ValueError):
            rubric_sensitivity(MockJudge(), [], RUBRICS)


class DetectionTest(unittest.TestCase):
    def test_a_judge_that_ignores_the_rubric_is_clean(self):
        report = rubric_sensitivity(IndifferentJudge(), CASES, RUBRICS)

        self.assertEqual(report.mean_spread, 0.0)
        self.assertEqual(report.max_spread, 0.0)
        self.assertEqual(report.widest_gap, 0.0)
        self.assertFalse(report.flagged)

    def test_a_wording_sensitive_judge_is_flagged(self):
        report = rubric_sensitivity(RubricFollowingJudge(), CASES, RUBRICS)

        self.assertGreater(report.max_spread, 0.15)
        self.assertTrue(report.flagged)

    def test_shape_matches_the_inputs(self):
        report = rubric_sensitivity(MockJudge(), CASES, RUBRICS)

        self.assertEqual(report.cases, len(CASES))
        self.assertEqual(report.variants, len(RUBRICS))
        self.assertEqual(len(report.variant_means), len(RUBRICS))

    def test_variant_means_stay_in_input_order(self):
        """The means are only actionable if you can tell which rubric is which."""
        report = rubric_sensitivity(RubricFollowingJudge(), CASES, RUBRICS)

        # This judge scores on rubric length, so the means must rank the same
        # way the rubrics do by length.
        by_length = sorted(range(len(RUBRICS)), key=lambda i: len(RUBRICS[i]))
        by_mean = sorted(
            range(len(RUBRICS)), key=lambda i: report.variant_means[i]
        )
        self.assertEqual(by_length, by_mean)

    def test_widest_gap_spans_most_and_least_generous(self):
        report = rubric_sensitivity(RubricFollowingJudge(), CASES, RUBRICS)

        self.assertAlmostEqual(
            report.widest_gap,
            max(report.variant_means) - min(report.variant_means),
        )

    def test_workers_do_not_change_the_result(self):
        serial = rubric_sensitivity(MockJudge(), CASES, RUBRICS)
        parallel = rubric_sensitivity(MockJudge(), CASES, RUBRICS, max_workers=4)

        self.assertEqual(serial.mean_spread, parallel.mean_spread)
        self.assertEqual(serial.variant_means, parallel.variant_means)


class ThresholdTest(unittest.TestCase):
    def test_tolerance_moves_the_verdict_not_the_measurement(self):
        strict = rubric_sensitivity(
            MockJudge(), CASES, RUBRICS,
            thresholds=Thresholds(rubric_mean_spread=0.0, rubric_max_spread=0.0),
        )
        loose = rubric_sensitivity(
            MockJudge(), CASES, RUBRICS,
            thresholds=Thresholds(rubric_mean_spread=1.0, rubric_max_spread=1.0),
        )

        self.assertTrue(strict.flagged)
        self.assertFalse(loose.flagged)
        self.assertEqual(strict.max_spread, loose.max_spread)


class CliTest(unittest.TestCase):
    PAYLOAD = {
        "rubrics": RUBRICS,
        "cases": [{"prompt": p, "good": r} for p, r in CASES],
    }

    def run_cli(self, payload, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.json"
            path.write_text(
                payload if isinstance(payload, str) else json.dumps(payload)
            )
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["rubric", str(path), *args])
            return code, out.getvalue(), err.getvalue()

    def test_reports_and_exits_one_when_sensitive(self):
        code, out, _ = self.run_cli(self.PAYLOAD)

        self.assertEqual(code, 1)
        self.assertIn("FLAGGED", out)
        self.assertIn("widest_gap", out)

    def test_json_pairs_each_rubric_with_its_mean(self):
        _, out, _ = self.run_cli(self.PAYLOAD, "--json")
        payload = json.loads(out)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["report"], "rubric")
        self.assertEqual(len(payload["rubrics"]), len(RUBRICS))
        self.assertEqual(payload["rubrics"][0]["rubric"], RUBRICS[0])
        self.assertIn("mean_score", payload["rubrics"][0])

    def test_response_key_is_accepted_as_well_as_good(self):
        payload = {
            "rubrics": RUBRICS,
            "cases": [{"prompt": p, "response": r} for p, r in CASES],
        }
        code, _, _ = self.run_cli(payload)

        self.assertIn(code, (0, 1))   # ran; verdict is not the point here

    def test_rejects_bad_input(self):
        for payload in (
            "{not json",
            {},
            {"rubrics": [RUBRICS[0]], "cases": [{"prompt": "p", "good": "g"}]},
            {"rubrics": RUBRICS, "cases": []},
            {"rubrics": RUBRICS, "cases": [{"prompt": "p"}]},
            {"rubrics": [RUBRICS[0], RUBRICS[0]],
             "cases": [{"prompt": "p", "good": "g"}]},   # identical wordings
            {"rubrics": [RUBRICS[0], ""],
             "cases": [{"prompt": "p", "good": "g"}]},
        ):
            with self.subTest(payload=payload):
                code, _, err = self.run_cli(payload)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("juryrig:"), err)


class LoaderTest(unittest.TestCase):
    def test_reads_rubrics_and_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.json"
            path.write_text(json.dumps({
                "rubrics": RUBRICS,
                "cases": [{"prompt": p, "good": r} for p, r in CASES],
            }))
            rubrics, cases, _ = load_rubric_variants(path)

        self.assertEqual(rubrics, RUBRICS)
        self.assertEqual(cases, CASES)


if __name__ == "__main__":
    unittest.main()
