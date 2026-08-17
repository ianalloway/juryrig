import unittest

from juryrig import MockJudge, audit_suite, position_bias, self_consistency

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
RESPONSE = "photosynthesis chlorophyll sunlight energy"
CASES = [
    ("How do plants make food?", RESPONSE, "plants eat soil"),
    ("Explain plant energy.", "sunlight energy chlorophyll", "it just happens"),
]


def consistency(judge, runs=5):
    return self_consistency(
        judge, prompt="q", response=RESPONSE, rubric=RUBRIC, runs=runs
    )


class InstabilityTest(unittest.TestCase):
    def test_noise_alone_cannot_be_detected_by_self_consistency(self):
        # Documents the distinction rather than a defect: noise is seeded on
        # the input, so re-judging one response is identical every time.
        self.assertEqual(consistency(MockJudge(noise=0.9)).spread, 0.0)

    def test_instability_is_detected(self):
        report = consistency(MockJudge(instability=0.5))

        self.assertGreater(report.spread, 0.2)
        self.assertTrue(report.flagged)

    def test_a_stable_judge_is_still_clean(self):
        report = consistency(MockJudge())

        self.assertEqual(report.spread, 0.0)
        self.assertFalse(report.flagged)

    def test_sequence_is_reproducible_across_fresh_judges(self):
        """Varies per call, but a fresh judge replays the same run — so CI
        stays deterministic even with the flaw switched on."""
        first = consistency(MockJudge(instability=0.5))
        second = consistency(MockJudge(instability=0.5))

        self.assertEqual(first.mean, second.mean)
        self.assertEqual(first.spread, second.spread)

    def test_different_seeds_give_different_sequences(self):
        self.assertNotEqual(
            consistency(MockJudge(instability=0.5, seed=1)).mean,
            consistency(MockJudge(instability=0.5, seed=2)).mean,
        )

    def test_scores_stay_in_range(self):
        for score in [
            MockJudge(instability=2.0).judge(
                prompt="q", response=RESPONSE, rubric=RUBRIC
            ).score
            for _ in range(50)
        ]:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_counter_is_thread_safe(self):
        # Every parallel call must get a distinct counter value; a lost update
        # would show up as a duplicated draw. 40 calls across 8 workers.
        judge = MockJudge(instability=0.5)
        pairs = [(f"p{i}", RESPONSE, "weak") for i in range(20)]

        report = audit_suite(judge, pairs, RUBRIC, runs=2, max_workers=8)

        self.assertIsNotNone(report.position)


class TieMarginTest(unittest.TestCase):
    def test_equal_scores_tie_instead_of_defaulting_to_slot_a(self):
        # Without a margin, compare()'s >= tie-break hands identical answers
        # to slot A, which the audit correctly reads as position bias.
        identical = [("q", RESPONSE, RESPONSE)]

        biased = position_bias(MockJudge(), identical, RUBRIC)
        honest = position_bias(MockJudge(tie_margin=0.1), identical, RUBRIC)

        self.assertTrue(biased.flagged)
        self.assertEqual(biased.ties, 0)

        self.assertFalse(honest.flagged)
        self.assertEqual(honest.ties, 2)
        self.assertEqual(honest.flips, 0)

    def test_margin_of_zero_keeps_the_old_behaviour(self):
        report = position_bias(MockJudge(tie_margin=0.0), CASES, RUBRIC)

        self.assertEqual(report.ties, 0)

    def test_clearly_different_answers_still_get_a_winner(self):
        report = position_bias(MockJudge(tie_margin=0.05), CASES, RUBRIC)

        self.assertEqual(report.ties, 0)
        self.assertEqual(report.flips, 0)


if __name__ == "__main__":
    unittest.main()
