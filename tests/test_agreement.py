"""Unit tests for the pairwise agreement / concordance matrix audit."""
import json
import unittest

from juryrig import (
    DEFAULT_AGREEMENT_THRESHOLDS,
    AgreementThresholds,
    Judgment,
    MockJudge,
    agreement_matrix,
    cohen_kappa,
)

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
PAIRS = [
    (
        "How do plants make food?",
        "Plants use photosynthesis: chlorophyll captures sunlight energy.",
    ),
    (
        "Explain plant energy.",
        "Through photosynthesis, sunlight energy is converted using chlorophyll.",
    ),
    (
        "Why are leaves green?",
        "Chlorophyll, the photosynthesis pigment that absorbs sunlight energy.",
    ),
]


class FixedScoreJudge:
    """Deterministic fake: returns a canned score per response text."""

    def __init__(self, name: str, scores: dict[str, float]) -> None:
        self.name = name
        self.scores = scores

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        return Judgment(score=self.scores[response])


class CohenKappaTest(unittest.TestCase):
    def test_perfect_agreement_is_one(self):
        labels = ["a", "b", "a", "c"]
        self.assertEqual(cohen_kappa(labels, list(labels)), 1.0)

    def test_chance_level_is_near_zero(self):
        # Both raters flip a fair coin independently on balanced labels → Pe≈0.5,
        # observed agreement also ≈0.5 when fully crossed.
        a = ["yes", "yes", "no", "no"]
        b = ["yes", "no", "yes", "no"]
        self.assertAlmostEqual(cohen_kappa(a, b), 0.0)

    def test_systematic_disagreement_is_negative(self):
        a = ["yes", "yes", "no", "no"]
        b = ["no", "no", "yes", "yes"]
        self.assertLess(cohen_kappa(a, b), 0.0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            cohen_kappa(["a"], ["a", "b"])

    def test_single_category_unanimous_is_one(self):
        self.assertEqual(cohen_kappa(["x", "x", "x"], ["x", "x", "x"]), 1.0)


class AgreementMatrixTest(unittest.TestCase):
    def test_identical_judges_agree_perfectly(self):
        report = agreement_matrix(
            [MockJudge(name="a", seed=0), MockJudge(name="b", seed=0)],
            PAIRS,
            RUBRIC,
            epsilon=0.0,
        )

        self.assertFalse(report.flagged)
        self.assertEqual(report.failures, ())
        pair = report.pairs[0]
        self.assertEqual(pair.exact_rate, 1.0)
        self.assertEqual(pair.within_eps_rate, 1.0)
        self.assertEqual(pair.kappa, 1.0)
        self.assertEqual(pair.mean_abs_delta, 0.0)

    def test_divergent_fakes_are_flagged(self):
        responses = [r for _, r in PAIRS]
        left = FixedScoreJudge(
            "strict", {responses[0]: 0.9, responses[1]: 0.8, responses[2]: 0.7}
        )
        right = FixedScoreJudge(
            "lenient", {responses[0]: 0.2, responses[1]: 0.1, responses[2]: 0.0}
        )
        report = agreement_matrix(
            [left, right],
            PAIRS,
            RUBRIC,
            epsilon=0.05,
            thresholds=AgreementThresholds(
                min_exact_rate=0.8,
                min_within_eps_rate=0.9,
                min_kappa=0.4,
            ),
        )

        self.assertTrue(report.flagged)
        self.assertEqual(report.failures, ("strict|lenient",))
        pair = report.pairs[0]
        self.assertEqual(pair.exact_rate, 0.0)
        self.assertEqual(pair.within_eps_rate, 0.0)
        self.assertLess(pair.kappa, 0.4)

    def test_within_epsilon_counts_near_matches(self):
        responses = [r for _, r in PAIRS]
        left = FixedScoreJudge(
            "a", {responses[0]: 0.50, responses[1]: 0.60, responses[2]: 0.70}
        )
        right = FixedScoreJudge(
            "b", {responses[0]: 0.54, responses[1]: 0.61, responses[2]: 0.90}
        )
        report = agreement_matrix([left, right], PAIRS, RUBRIC, epsilon=0.05)

        pair = report.pairs[0]
        # First two within 0.05, third is 0.20 away.
        self.assertAlmostEqual(pair.within_eps_rate, 2 / 3)
        self.assertEqual(pair.exact_rate, 0.0)

    def test_rate_matrix_is_symmetric_with_unit_diagonal(self):
        report = agreement_matrix(
            [
                MockJudge(name="x", seed=0),
                MockJudge(name="y", seed=1),
                MockJudge(name="z", seed=2),
            ],
            PAIRS,
            RUBRIC,
        )
        grid = report.rate_matrix(metric="within_eps")

        self.assertEqual(len(grid), 3)
        for i in range(3):
            self.assertEqual(grid[i][i], 1.0)
            for j in range(3):
                self.assertEqual(grid[i][j], grid[j][i])

    def test_matrix_ascii_and_markdown_are_printable(self):
        report = agreement_matrix(
            [MockJudge(name="alpha"), MockJudge(name="beta")],
            PAIRS,
            RUBRIC,
        )
        ascii_table = report.matrix(fmt="ascii")
        md_table = report.matrix(fmt="markdown")

        self.assertIn("alpha", ascii_table)
        self.assertIn("1.00", ascii_table)
        self.assertIn("|", md_table)
        self.assertIn("agreement matrix", md_table)

    def test_to_dict_is_json_serializable(self):
        report = agreement_matrix(
            [MockJudge(name="a"), MockJudge(name="b")],
            PAIRS,
            RUBRIC,
        )
        payload = report.to_dict()
        # Round-trip through JSON to catch non-serializable values.
        restored = json.loads(json.dumps(payload))

        self.assertEqual(restored["judges"], ["a", "b"])
        self.assertEqual(restored["cases"], 3)
        self.assertIn("matrices", restored)
        self.assertEqual(len(restored["pairs"]), 1)

    def test_rejects_duplicate_names_and_thin_inputs(self):
        with self.assertRaises(ValueError):
            agreement_matrix(
                [MockJudge(name="same"), MockJudge(name="same")], PAIRS, RUBRIC
            )
        with self.assertRaises(ValueError):
            agreement_matrix([MockJudge()], PAIRS, RUBRIC)
        with self.assertRaises(ValueError):
            agreement_matrix(
                [MockJudge(name="a"), MockJudge(name="b")], [], RUBRIC
            )

    def test_default_thresholds_are_exported(self):
        self.assertEqual(DEFAULT_AGREEMENT_THRESHOLDS.min_kappa, 0.4)
        self.assertEqual(DEFAULT_AGREEMENT_THRESHOLDS.min_exact_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
