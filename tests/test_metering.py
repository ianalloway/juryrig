"""Call and latency accounting for a judge under audit."""
from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from juryrig import (
    Judgment,
    MockJudge,
    PairwiseJudge,
    UsageReport,
    audit_suite,
    metered,
    position_bias,
    verbosity_bias,
)
from juryrig.cli import main

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [
    ("q1", "photosynthesis chlorophyll sunlight energy", "soil"),
    ("q2", "sunlight energy chlorophyll", "nothing"),
]
CASE_FILE = {
    "rubric": RUBRIC,
    "cases": [{"prompt": p, "good": g, "weak": w} for p, g, w in CASES],
}


class ScoreOnlyJudge:
    name = "score-only"

    def judge(self, *, prompt, response, rubric):
        return Judgment(score=0.5)


class FakeClock:
    """Advances a fixed amount per reading, so timings are deterministic."""

    def __init__(self, step=0.5):
        self.step = step
        self.now = 0.0

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


class ShapePreservationTest(unittest.TestCase):
    """The wrapper must not change what a judge appears able to do."""

    def test_pairwise_judge_stays_pairwise(self):
        self.assertIsInstance(metered(MockJudge()), PairwiseJudge)

    def test_score_only_judge_does_not_gain_a_compare(self):
        # The trap this guards: audit_suite() decides whether to run the
        # position audit by checking for compare(). A wrapper that always had
        # one would make this judge look pairwise and undo the skipped-audit
        # reporting.
        wrapped = metered(ScoreOnlyJudge())

        self.assertNotIsInstance(wrapped, PairwiseJudge)
        self.assertFalse(hasattr(wrapped, "compare"))

    def test_skipped_audit_reporting_survives_metering(self):
        report = audit_suite(metered(ScoreOnlyJudge()), CASES, RUBRIC)

        self.assertEqual(report.skipped, ("position",))
        self.assertIn("position", report.skipped_reasons)

    def test_name_is_preserved(self):
        self.assertEqual(metered(MockJudge(name="fair")).name, "fair")

    def test_inner_judge_is_reachable(self):
        inner = MockJudge()
        self.assertIs(metered(inner).inner, inner)


class CountingTest(unittest.TestCase):
    def test_counts_judge_calls(self):
        judge = metered(MockJudge())
        verbosity_bias(judge, [(p, g) for p, g, _ in CASES], RUBRIC)

        # Two judge() calls per case: base and padded.
        self.assertEqual(judge.usage().judge_calls, 2 * len(CASES))
        self.assertEqual(judge.usage().compare_calls, 0)

    def test_counts_compare_calls(self):
        judge = metered(MockJudge())
        position_bias(judge, CASES, RUBRIC)

        # Two compare() calls per case: forward and backward.
        self.assertEqual(judge.usage().compare_calls, 2 * len(CASES))
        self.assertEqual(judge.usage().judge_calls, 0)

    def test_calls_totals_both_kinds(self):
        judge = metered(MockJudge())
        audit_suite(judge, CASES, RUBRIC)
        usage = judge.usage()

        self.assertEqual(usage.calls, usage.judge_calls + usage.compare_calls)
        self.assertGreater(usage.judge_calls, 0)
        self.assertGreater(usage.compare_calls, 0)

    def test_a_failed_call_is_still_counted(self):
        """A request that raises still cost time, and may still be billed."""

        class ExplodingJudge:
            name = "exploding"

            def judge(self, *, prompt, response, rubric):
                raise RuntimeError("upstream is down")

        judge = metered(ExplodingJudge())
        with self.assertRaises(RuntimeError):
            judge.judge(prompt="p", response="r", rubric=RUBRIC)

        self.assertEqual(judge.usage().judge_calls, 1)

    def test_counter_is_thread_safe(self):
        judge = metered(MockJudge())
        audit_suite(judge, CASES, RUBRIC, max_workers=8)
        serial = metered(MockJudge())
        audit_suite(serial, CASES, RUBRIC)

        # Same work either way; a lost update under parallelism would show up
        # as a lower count.
        self.assertEqual(judge.usage().calls, serial.usage().calls)

    def test_concurrent_calls_do_not_lose_counts(self):
        judge = metered(MockJudge())

        def hammer():
            for _ in range(50):
                judge.judge(prompt="p", response="r", rubric=RUBRIC)

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(judge.usage().judge_calls, 200)


class TimingTest(unittest.TestCase):
    def test_seconds_accumulate_per_call(self):
        judge = metered(MockJudge(), clock=FakeClock(step=0.5))
        judge.judge(prompt="p", response="r", rubric=RUBRIC)

        # One call reads the clock twice: 0.0 then 0.5.
        self.assertAlmostEqual(judge.usage().seconds, 0.5)

    def test_seconds_per_call_and_projection(self):
        judge = metered(MockJudge(), clock=FakeClock(step=0.5))
        for _ in range(4):
            judge.judge(prompt="p", response="r", rubric=RUBRIC)
        usage = judge.usage()

        self.assertAlmostEqual(usage.seconds_per_call, 0.5)
        self.assertAlmostEqual(usage.projected_seconds(100), 50.0)

    def test_projection_rejects_negative_calls(self):
        with self.assertRaises(ValueError):
            UsageReport(1, 0, 1.0).projected_seconds(-1)

    def test_empty_usage_does_not_divide_by_zero(self):
        usage = metered(MockJudge()).usage()

        self.assertEqual(usage.calls, 0)
        self.assertEqual(usage.seconds_per_call, 0.0)
        self.assertEqual(usage.projected_seconds(10), 0.0)


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(CASE_FILE))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(path), *args])
            return code, out.getvalue(), err.getvalue()

    def test_text_output_reports_usage(self):
        _, out, _ = self.run_cli()

        self.assertIn("usage", out)
        self.assertIn("calls=", out)

    def test_json_output_reports_usage(self):
        _, out, _ = self.run_cli("--json")
        payload = json.loads(out)

        self.assertIn("usage", payload)
        self.assertEqual(
            payload["usage"]["calls"],
            payload["usage"]["judge_calls"] + payload["usage"]["compare_calls"],
        )
        self.assertGreater(payload["usage"]["calls"], 0)

    def test_metering_does_not_change_the_verdict(self):
        code, out, _ = self.run_cli("--json")
        payload = json.loads(out)

        self.assertEqual(code, 0)
        self.assertFalse(payload["flagged"])
        self.assertEqual(payload["skipped"], [])


if __name__ == "__main__":
    unittest.main()
