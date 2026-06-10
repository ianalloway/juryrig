import unittest

from juryrig import MockJudge, position_bias, self_consistency, verbosity_bias

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


class PositionBiasTest(unittest.TestCase):
    def test_fair_judge_not_flagged(self):
        report = position_bias(MockJudge(), CASES, RUBRIC)
        self.assertEqual(report.flips, 0)
        self.assertFalse(report.flagged)

    def test_biased_judge_flagged(self):
        rigged = MockJudge(position_bias=2.0)  # always prefers slot A
        report = position_bias(rigged, CASES, RUBRIC)
        self.assertEqual(report.flip_rate, 1.0)
        self.assertEqual(report.first_slot_wins, 1.0)
        self.assertTrue(report.flagged)


class VerbosityBiasTest(unittest.TestCase):
    PAIRS = [(p, good) for p, good, _ in CASES]

    def test_fair_judge_not_flagged(self):
        report = verbosity_bias(MockJudge(), self.PAIRS, RUBRIC)
        self.assertFalse(report.flagged)

    def test_verbose_judge_flagged(self):
        windbag = MockJudge(verbosity_bias=0.4)
        report = verbosity_bias(windbag, self.PAIRS, RUBRIC)
        self.assertGreater(report.mean_delta, 0.05)
        self.assertTrue(report.flagged)


class ConsistencyTest(unittest.TestCase):
    def test_deterministic_judge_has_zero_spread(self):
        report = self_consistency(
            MockJudge(),
            prompt="q",
            response="photosynthesis chlorophyll sunlight energy",
            rubric=RUBRIC,
            runs=5,
        )
        self.assertEqual(report.spread, 0.0)
        self.assertFalse(report.flagged)


if __name__ == "__main__":
    unittest.main()
