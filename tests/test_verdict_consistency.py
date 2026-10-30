"""Verdict stability of a pairwise judge re-comparing one fixed ordering."""
from __future__ import annotations

import itertools
import threading
import unittest

from juryrig import MockJudge, Thresholds
from juryrig.audits import verdict_consistency

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
GOOD = "photosynthesis chlorophyll sunlight energy"
WEAK = "plants eat soil"


class CyclingJudge:
    """Returns a fixed repeating sequence of verdicts."""

    def __init__(self, sequence, name="cycling"):
        self.name = name
        self._it = itertools.cycle(sequence)
        self._lock = threading.Lock()

    def compare(self, *, prompt, a, b, rubric):
        with self._lock:
            return next(self._it)


def run(judge, runs=5, thresholds=None):
    kwargs = {"thresholds": thresholds} if thresholds else {}
    return verdict_consistency(
        judge, prompt="q", a=GOOD, b=WEAK, rubric=RUBRIC, runs=runs, **kwargs
    )


class StableJudgeTest(unittest.TestCase):
    def test_a_firm_judge_is_unanimous(self):
        report = run(MockJudge())

        self.assertEqual(report.stability, 1.0)
        self.assertTrue(report.unanimous)
        self.assertFalse(report.flagged)
        self.assertEqual(report.counts, {report.modal_verdict: 5})

    def test_single_run_is_trivially_stable(self):
        self.assertEqual(run(MockJudge(), runs=1).stability, 1.0)


class WaveringJudgeTest(unittest.TestCase):
    def test_a_wavering_judge_is_flagged(self):
        report = run(CyclingJudge(["A", "B"]))

        self.assertEqual(report.stability, 0.6)   # 3 of 5 to the mode
        self.assertFalse(report.unanimous)
        self.assertTrue(report.flagged)

    def test_counts_record_every_verdict_seen(self):
        report = run(CyclingJudge(["A", "B", "tie"]), runs=6)

        self.assertEqual(sum(report.counts.values()), 6)
        self.assertEqual(set(report.counts), {"A", "B", "tie"})
        self.assertAlmostEqual(report.stability, 2 / 6)

    def test_modal_verdict_is_the_most_common_one(self):
        report = run(CyclingJudge(["A", "A", "A", "B", "B"]))

        self.assertEqual(report.modal_verdict, "A")
        self.assertAlmostEqual(report.stability, 3 / 5)


class ThresholdTest(unittest.TestCase):
    def test_stability_is_a_floor_not_a_ceiling(self):
        # Every other threshold caps a defect; this one sets a minimum, so a
        # LOWER threshold is the more permissive one.
        judge = CyclingJudge(["A", "B"])
        strict = run(judge, thresholds=Thresholds(verdict_stability=0.9))
        judge2 = CyclingJudge(["A", "B"])
        loose = run(judge2, thresholds=Thresholds(verdict_stability=0.5))

        self.assertTrue(strict.flagged)
        self.assertFalse(loose.flagged)

    def test_report_carries_its_thresholds(self):
        custom = Thresholds(verdict_stability=0.42)
        self.assertEqual(run(MockJudge(), thresholds=custom).thresholds, custom)

    def test_rejects_zero_runs(self):
        with self.assertRaises(ValueError):
            run(MockJudge(), runs=0)


class SeparatesInstabilityFromPositionBiasTest(unittest.TestCase):
    def test_a_wavering_judge_can_look_positionally_clean(self):
        """Why this audit exists.

        position_bias() shows each ordering once, so a judge that merely
        alternates can produce a flip rate that looks fine while its verdicts
        are worthless. Only re-running a fixed ordering reveals it.
        """
        from juryrig import position_bias

        cases = [("q1", GOOD, WEAK), ("q2", GOOD, WEAK)]
        alternating = CyclingJudge(["A", "B"])
        position = position_bias(alternating, cases, RUBRIC)

        unstable = run(CyclingJudge(["A", "B"]))

        self.assertFalse(position.flagged)   # position audit sees nothing
        self.assertTrue(unstable.flagged)    # this one does


if __name__ == "__main__":
    unittest.main()
