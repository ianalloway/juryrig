import unittest

from juryrig import Judgment, MockJudge, Panel

RUBRIC = "mention photosynthesis chlorophyll sunlight energy"
GOOD = "Photosynthesis uses chlorophyll to turn sunlight into energy."
WEAK = "Plants eat soil."


class FixedVoteJudge:
    """Pairwise judge that always votes the same slot."""

    def __init__(self, name, vote):
        self.name = name
        self.vote = vote

    def compare(self, *, prompt, a, b, rubric):
        return self.vote


class ScoreOnlyJudge:
    """Has judge() but no compare() — cannot sit on a pairwise panel."""

    name = "score-only"

    def judge(self, *, prompt, response, rubric):
        return Judgment(score=0.5)


class PanelCompareTest(unittest.TestCase):
    def compare(self, judges, a=GOOD, b=WEAK):
        return Panel(judges).compare(prompt="q", a=a, b=b, rubric=RUBRIC)

    def test_unanimous_panel_backs_the_better_answer(self):
        verdict = self.compare([MockJudge(name="a"), MockJudge(name="b")])

        self.assertEqual(verdict.winner, "A")
        self.assertTrue(verdict.unanimous)
        self.assertEqual(verdict.agreement, 1.0)
        self.assertFalse(verdict.deadlocked)

    def test_majority_wins_and_agreement_reports_the_split(self):
        verdict = self.compare([
            FixedVoteJudge("x", "A"),
            FixedVoteJudge("y", "A"),
            FixedVoteJudge("z", "B"),
        ])

        self.assertEqual(verdict.winner, "A")
        self.assertAlmostEqual(verdict.agreement, 2 / 3)
        self.assertFalse(verdict.unanimous)

    def test_even_split_is_reported_as_deadlock_not_a_coin_flip(self):
        verdict = self.compare([
            FixedVoteJudge("x", "A"),
            FixedVoteJudge("y", "B"),
        ])

        self.assertIsNone(verdict.winner)
        self.assertTrue(verdict.deadlocked)
        self.assertFalse(verdict.unanimous)

    def test_every_vote_is_recorded(self):
        verdict = self.compare([
            FixedVoteJudge("x", "A"),
            FixedVoteJudge("y", "B"),
            FixedVoteJudge("z", "B"),
        ])

        self.assertEqual(verdict.votes, {"x": "A", "y": "B", "z": "B"})
        self.assertEqual(verdict.winner, "B")

    def test_scoring_only_judge_is_rejected_by_name(self):
        panel = Panel([MockJudge(name="ok"), ScoreOnlyJudge()])

        with self.assertRaises(TypeError) as caught:
            panel.compare(prompt="q", a=GOOD, b=WEAK, rubric=RUBRIC)

        # Naming the offender matters — silently dropping it would change the
        # verdict while leaving agreement looking healthy.
        self.assertIn("score-only", str(caught.exception))

    def test_single_judge_panel_is_unanimous(self):
        verdict = self.compare([MockJudge(name="solo")])

        self.assertEqual(verdict.winner, "A")
        self.assertEqual(verdict.agreement, 1.0)


if __name__ == "__main__":
    unittest.main()
