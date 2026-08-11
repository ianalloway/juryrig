import unittest

from juryrig import MockJudge, PairwiseJudge, Panel, position_bias

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [
    ("How do plants make food?", "photosynthesis chlorophyll", "plants eat soil"),
    ("Explain plant energy.", "sunlight energy chlorophyll", "it just happens"),
]


class ScriptedJudge:
    """Replays a fixed list of verdicts, one per compare() call."""

    def __init__(self, verdicts, name="scripted"):
        self.name = name
        self._verdicts = list(verdicts)
        self.calls = 0

    def compare(self, *, prompt, a, b, rubric):
        verdict = self._verdicts[self.calls % len(self._verdicts)]
        self.calls += 1
        return verdict


class AlwaysTies(ScriptedJudge):
    def __init__(self, name="always-ties"):
        super().__init__(["tie"], name=name)


class ProtocolTest(unittest.TestCase):
    def test_tie_capable_judge_satisfies_the_protocol(self):
        self.assertIsInstance(AlwaysTies(), PairwiseJudge)

    def test_judges_that_never_tie_are_unaffected(self):
        # Widening the return type must not break an existing A/B-only judge.
        self.assertIsInstance(MockJudge(), PairwiseJudge)


class PositionBiasWithTiesTest(unittest.TestCase):
    def test_consistent_ties_are_not_flips(self):
        """Tying both ways is the judge being consistent, not order-driven."""
        report = position_bias(AlwaysTies(), CASES, RUBRIC)

        self.assertEqual(report.flips, 0)
        self.assertEqual(report.ties, 2 * len(CASES))

    def test_all_ties_is_not_reported_as_bias(self):
        # The trap: counting ties as "not won by slot one" would put
        # first_slot_wins at 0.0 and flag a judge that never favoured a slot
        # at all. With nothing decisive, 0.5 is the honest answer.
        report = position_bias(AlwaysTies(), CASES, RUBRIC)

        self.assertEqual(report.first_slot_wins, 0.5)
        self.assertFalse(report.flagged)

    def test_tie_one_way_and_a_pick_the_other_is_a_flip(self):
        # Verdict changed when the order changed — that is position bias,
        # even though one of the two verdicts was a tie.
        report = position_bias(ScriptedJudge(["A", "tie"]), CASES, RUBRIC)

        self.assertEqual(report.flips, len(CASES))
        self.assertEqual(report.ties, len(CASES))

    def test_ties_excluded_from_the_slot_ratio(self):
        # Per case: forward "A" (slot one), backward "tie" (ignored).
        # Every decisive verdict went to slot one, so the ratio is 1.0.
        report = position_bias(ScriptedJudge(["A", "tie"]), CASES, RUBRIC)

        self.assertEqual(report.first_slot_wins, 1.0)
        self.assertTrue(report.flagged)

    def test_slot_biased_judge_still_caught_among_ties(self):
        # Two cases: one all-tie, one always-slot-one. The tie must not
        # dilute the evidence from the case that did show a preference.
        report = position_bias(
            ScriptedJudge(["tie", "tie", "A", "A"]), CASES, RUBRIC
        )

        self.assertEqual(report.first_slot_wins, 1.0)
        self.assertEqual(report.ties, 2)
        self.assertTrue(report.flagged)

    def test_no_ties_behaves_exactly_as_before(self):
        report = position_bias(MockJudge(), CASES, RUBRIC)

        self.assertEqual(report.ties, 0)
        self.assertEqual(report.first_slot_wins, 0.5)
        self.assertFalse(report.flagged)


class PanelWithTiesTest(unittest.TestCase):
    def compare(self, judges):
        return Panel(judges).compare(prompt="q", a="x", b="y", rubric=RUBRIC)

    def test_panel_agreeing_on_a_tie_has_no_winner_but_full_agreement(self):
        verdict = self.compare([AlwaysTies("t1"), AlwaysTies("t2")])

        self.assertIsNone(verdict.winner)
        self.assertEqual(verdict.agreement, 1.0)
        self.assertEqual(set(verdict.votes.values()), {"tie"})

    def test_tie_votes_do_not_beat_a_real_majority(self):
        verdict = self.compare([
            ScriptedJudge(["A"], name="a1"),
            ScriptedJudge(["A"], name="a2"),
            AlwaysTies("t1"),
        ])

        self.assertEqual(verdict.winner, "A")
        self.assertAlmostEqual(verdict.agreement, 2 / 3)

    def test_tie_plurality_yields_no_winner(self):
        verdict = self.compare([
            AlwaysTies("t1"),
            AlwaysTies("t2"),
            ScriptedJudge(["A"], name="a1"),
        ])

        self.assertIsNone(verdict.winner)
        self.assertAlmostEqual(verdict.agreement, 2 / 3)


if __name__ == "__main__":
    unittest.main()
