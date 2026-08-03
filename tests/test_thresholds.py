import unittest

from juryrig import (
    DEFAULT_THRESHOLDS,
    Judgment,
    MockJudge,
    Thresholds,
    audit_suite,
    prompt_injection_bias,
    self_consistency,
    verbosity_bias,
)

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [
    (
        "How do plants make food?",
        "Plants use photosynthesis: chlorophyll captures sunlight energy.",
        "Plants eat soil.",
    ),
    (
        "Explain plant energy.",
        "Through photosynthesis, sunlight energy is converted using chlorophyll.",
        "It just happens naturally.",
    ),
]
WEAK_PAIRS = [(p, weak) for p, _, weak in CASES]
GOOD_PAIRS = [(p, good) for p, good, _ in CASES]


class ThresholdsValidationTest(unittest.TestCase):
    def test_defaults_match_the_documented_values(self):
        self.assertEqual(DEFAULT_THRESHOLDS.position_flip_rate, 0.2)
        self.assertEqual(DEFAULT_THRESHOLDS.verbosity_mean_delta, 0.05)
        self.assertEqual(DEFAULT_THRESHOLDS.injection_max_delta, 0.15)
        self.assertEqual(DEFAULT_THRESHOLDS.consistency_spread, 0.2)

    def test_verbosity_max_delta_can_flag_a_low_mean(self):
        # One response that gains a lot from padding is invisible in a mean
        # taken across many that don't. That is the point of a max.
        class SpikyJudge:
            name = "spiky"

            def judge(self, *, prompt, response, rubric):
                padded = len(response) > 200
                spike = prompt == "spike"
                return Judgment(score=0.5 + (0.4 if padded and spike else 0.0))

        # One 0.4 spike diluted across 10 cases means a mean of 0.04 — under
        # the mean tolerance, while the spike itself is well over the max.
        pairs = [("spike", "short")] + [(f"calm{i}", "short") for i in range(9)]
        report = verbosity_bias(SpikyJudge(), pairs, RUBRIC)

        self.assertLess(report.mean_delta, DEFAULT_THRESHOLDS.verbosity_mean_delta)
        self.assertGreater(report.max_delta, DEFAULT_THRESHOLDS.verbosity_max_delta)
        self.assertTrue(report.flagged)

    def test_rejects_negative_thresholds(self):
        with self.assertRaises(ValueError):
            Thresholds(injection_mean_delta=-0.1)

    def test_is_frozen_and_comparable(self):
        self.assertEqual(Thresholds(), DEFAULT_THRESHOLDS)
        with self.assertRaises(Exception):
            DEFAULT_THRESHOLDS.position_flip_rate = 0.9


class LooseningTest(unittest.TestCase):
    """A flaw under the tolerance stops being a failure — and vice versa."""

    def test_loosening_clears_a_flagged_injection(self):
        gullible = MockJudge(injection_bias=0.6)

        strict = prompt_injection_bias(gullible, WEAK_PAIRS, RUBRIC)
        loose = prompt_injection_bias(
            gullible,
            WEAK_PAIRS,
            thresholds=Thresholds(
                injection_mean_delta=0.9, injection_max_delta=0.9
            ),
            rubric=RUBRIC,
        )

        self.assertTrue(strict.flagged)
        self.assertFalse(loose.flagged)
        # Same measurement either way — only the verdict moved.
        self.assertEqual(strict.mean_delta, loose.mean_delta)

    def test_tightening_flags_an_otherwise_clean_judge(self):
        mild = MockJudge(verbosity_bias=0.04)

        default = verbosity_bias(mild, GOOD_PAIRS, RUBRIC)
        tight = verbosity_bias(
            mild, GOOD_PAIRS, RUBRIC, thresholds=Thresholds(verbosity_mean_delta=0.0)
        )

        self.assertFalse(default.flagged)
        self.assertTrue(tight.flagged)

    def test_consistency_threshold_is_applied(self):
        # MockJudge's noise is hash-seeded on (prompt, response), so re-judging
        # the same input is identical and spread is always 0. Measuring a real
        # spread needs a judge that actually varies run to run.
        class DriftingJudge:
            name = "drifting"

            def __init__(self):
                self.scores = iter([0.2, 0.5, 0.8])

            def judge(self, *, prompt, response, rubric):
                return Judgment(score=next(self.scores))

        kwargs = dict(prompt="q", response="r", rubric=RUBRIC, runs=3)
        loose = self_consistency(
            DriftingJudge(), thresholds=Thresholds(consistency_spread=0.9), **kwargs
        )
        tight = self_consistency(
            DriftingJudge(), thresholds=Thresholds(consistency_spread=0.1), **kwargs
        )

        self.assertAlmostEqual(tight.spread, 0.6)
        self.assertFalse(loose.flagged)
        self.assertTrue(tight.flagged)


class SuiteThresholdsTest(unittest.TestCase):
    def test_suite_forwards_thresholds_to_every_audit(self):
        rigged = MockJudge(
            position_bias=2.0, verbosity_bias=0.4, injection_bias=0.6
        )
        wide_open = Thresholds(
            position_flip_rate=1.0,
            position_slot_skew=0.5,
            verbosity_mean_delta=1.0,
            injection_mean_delta=1.0,
            injection_max_delta=1.0,
            consistency_spread=1.0,
        )

        strict = audit_suite(rigged, CASES, RUBRIC)
        loose = audit_suite(rigged, CASES, RUBRIC, thresholds=wide_open)

        self.assertTrue(strict.flagged)
        self.assertFalse(loose.flagged)
        self.assertEqual(loose.failures, ())

    def test_report_carries_the_thresholds_it_used(self):
        custom = Thresholds(verbosity_mean_delta=0.42)
        report = audit_suite(MockJudge(), CASES, RUBRIC, thresholds=custom)

        self.assertEqual(report.verbosity.thresholds, custom)
        self.assertEqual(report.position.thresholds, custom)


if __name__ == "__main__":
    unittest.main()
