"""Unit tests for the disagreement atlas (built on agreement-matrix scores)."""
import json
import math
import unittest

from juryrig import (
    AgreementMatrixReport,
    Judgment,
    agreement_matrix,
    disagreement_atlas,
    disagreement_atlas_from_report,
)
from juryrig.atlas import (
    _population_variance,
    _shannon_entropy,
)


class FixedScoreJudge:
    """Deterministic fake: returns a canned score per response text.

    Lookups are by response string only — no hashing of prompts, no RNG.
    """

    def __init__(self, name: str, scores: dict[str, float]) -> None:
        self.name = name
        self.scores = scores

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        return Judgment(score=self.scores[response])


RUBRIC = "r"
# Four items with *distinct* variance ranks and known split patterns.
# Variances (population) are intentionally well-separated so platform float
# noise cannot reorder them:
#   0: all agree (0.5, 0.5, 0.5)           var = 0
#   1: a vs b,c  (1.0, 0.0, 0.0)           var = 8/27 ≈ 0.296  pairs a|b, a|c
#   2: a,b vs c  (0.8, 0.8, 0.0)           var = 32/225 ≈ 0.142 pairs a|c, b|c
#   3: three-way (0.0, 0.5, 1.0)           var = 1/6 ≈ 0.167   all pairs
# Variance ranking (desc): 1 > 3 > 2 > 0
CASES = [
    ("p0", "r0"),
    ("p1", "r1"),
    ("p2", "r2"),
    ("p3", "r3"),
]
JUDGES = [
    FixedScoreJudge("a", {"r0": 0.5, "r1": 1.0, "r2": 0.8, "r3": 0.0}),
    FixedScoreJudge("b", {"r0": 0.5, "r1": 0.0, "r2": 0.8, "r3": 0.5}),
    FixedScoreJudge("c", {"r0": 0.5, "r1": 0.0, "r2": 0.0, "r3": 1.0}),
]


def _atlas(**kwargs):
    return disagreement_atlas(JUDGES, CASES, RUBRIC, epsilon=0.05, **kwargs)


class HelpersTest(unittest.TestCase):
    def test_population_variance_known_values(self):
        self.assertEqual(_population_variance([1.0]), 0.0)
        self.assertAlmostEqual(_population_variance([1.0, 3.0]), 1.0)
        self.assertAlmostEqual(_population_variance([2.0, 2.0, 2.0]), 0.0)

    def test_fixture_variances_are_strictly_ordered(self):
        """Guard against accidental equal-variance fixtures (CI flake source)."""
        vars_ = [
            _population_variance([0.5, 0.5, 0.5]),
            _population_variance([1.0, 0.0, 0.0]),
            _population_variance([0.8, 0.8, 0.0]),
            _population_variance([0.0, 0.5, 1.0]),
        ]
        # Ranking desc must be item 1, 3, 2, 0 with clear gaps.
        self.assertGreater(vars_[1], vars_[3])
        self.assertGreater(vars_[3], vars_[2])
        self.assertGreater(vars_[2], vars_[0])

    def test_shannon_entropy_uniform_and_degenerate(self):
        self.assertEqual(_shannon_entropy(["x", "x", "x"]), 0.0)
        self.assertAlmostEqual(_shannon_entropy(["a", "b"]), 1.0)
        # Three distinct labels → log2(3)
        self.assertAlmostEqual(
            _shannon_entropy(["a", "b", "c"]), math.log2(3)
        )


class DisagreementAtlasTest(unittest.TestCase):
    def test_ranks_by_variance_highest_first(self):
        atlas = _atlas(ranking="variance")
        self.assertEqual([item.index for item in atlas.items], [1, 3, 2, 0])
        self.assertGreater(atlas.items[0].variance, atlas.items[1].variance)
        self.assertGreater(atlas.items[1].variance, atlas.items[2].variance)
        self.assertGreater(atlas.items[2].variance, atlas.items[3].variance)
        self.assertEqual(atlas.items[-1].variance, 0.0)
        self.assertEqual(atlas.items[-1].split_pairs, ())

    def test_pairwise_ranking_and_split_pairs(self):
        atlas = _atlas(ranking="pairwise")
        by_index = {item.index: item for item in atlas.items}

        self.assertEqual(by_index[0].pairwise_disagreement, 0.0)
        self.assertEqual(by_index[0].split_pairs, ())
        # Item 1: a disagrees with b and c → 2/3 of pairs.
        self.assertAlmostEqual(by_index[1].pairwise_disagreement, 2 / 3)
        self.assertEqual(by_index[1].split_pairs, ("a|b", "a|c"))
        # Item 3: every pair disagrees.
        self.assertEqual(by_index[3].pairwise_disagreement, 1.0)
        self.assertEqual(by_index[3].split_pairs, ("a|b", "a|c", "b|c"))
        # Pairwise ranking: item 3 (1.0) > items 1 & 2 (2/3) > item 0 (0).
        # Tie between 1 and 2 broken by index ascending → [3, 1, 2, 0].
        self.assertEqual([item.index for item in atlas.items], [3, 1, 2, 0])

    def test_entropy_ranking_for_categorical_splits(self):
        atlas = _atlas(ranking="entropy", kappa_decimals=1)
        by_index = {item.index: item for item in atlas.items}

        self.assertEqual(by_index[0].entropy, 0.0)
        # Item 1: labels {1.0, 0.0, 0.0} → two categories, not uniform.
        self.assertGreater(by_index[1].entropy, 0.0)
        self.assertLess(by_index[1].entropy, math.log2(3))
        # Item 3: three distinct buckets → max entropy among items.
        self.assertAlmostEqual(by_index[3].entropy, math.log2(3))
        self.assertEqual(atlas.items[0].index, 3)

    def test_clusters_sorted_by_size_then_signature(self):
        atlas = _atlas()
        # Four singleton signatures → size ties broken lexicographically.
        signatures = [cluster.split_pairs for cluster in atlas.clusters]
        self.assertEqual(
            signatures,
            [
                (),
                ("a|b", "a|c"),
                ("a|b", "a|c", "b|c"),
                ("a|c", "b|c"),
            ],
        )
        by_sig = {c.split_pairs: c.item_indices for c in atlas.clusters}
        self.assertEqual(by_sig[("a|b", "a|c")], (1,))
        self.assertEqual(by_sig[()], (0,))

    def test_ranking_tie_breaks_by_index_ascending(self):
        """Equal ranking scores must order by item index, never by hash/RNG."""
        judges = [
            FixedScoreJudge("a", {"r0": 1.0, "r1": 0.0, "r2": 0.5}),
            FixedScoreJudge("b", {"r0": 0.0, "r1": 1.0, "r2": 0.5}),
        ]
        # Items 0 and 1 are mirror images → identical variance & pairwise;
        # item 2 is unanimous. Ranking desc + index asc → [0, 1, 2].
        cases = [("p0", "r0"), ("p1", "r1"), ("p2", "r2")]
        atlas = disagreement_atlas(judges, cases, RUBRIC, epsilon=0.05)

        self.assertAlmostEqual(atlas.items[0].variance, atlas.items[1].variance)
        self.assertEqual([item.index for item in atlas.items], [0, 1, 2])

    def test_clusters_group_and_order_by_size_then_lex(self):
        """Two items share a signature → that cluster sorts ahead of singletons."""
        judges = [
            FixedScoreJudge(
                "a", {"r0": 1.0, "r1": 1.0, "r2": 0.0, "r3": 0.5}
            ),
            FixedScoreJudge(
                "b", {"r0": 0.0, "r1": 0.0, "r2": 1.0, "r3": 0.5}
            ),
            FixedScoreJudge(
                "c", {"r0": 0.0, "r1": 0.0, "r2": 0.0, "r3": 0.5}
            ),
        ]
        # 0 & 1: same split a|b, a|c (a high, b&c low)
        # 2: split a|b, b|c (b high, a&c low)
        # 3: unanimous
        cases = [("p0", "r0"), ("p1", "r1"), ("p2", "r2"), ("p3", "r3")]
        atlas = disagreement_atlas(judges, cases, RUBRIC, epsilon=0.05)

        self.assertEqual(
            [c.split_pairs for c in atlas.clusters],
            [
                ("a|b", "a|c"),  # size 2
                (),  # size 1, lex first among remaining
                ("a|b", "b|c"),  # size 1
            ],
        )
        self.assertEqual(atlas.clusters[0].item_indices, (0, 1))

    def test_contrarian_rates_vs_median(self):
        atlas = _atlas()
        rates = {entry.judge: entry for entry in atlas.contrarian}

        # Item 0: all at median. Item 1: a is the outlier. Item 2: c is.
        # Item 3: median is 0.5 (b); a and c are both away.
        self.assertEqual(rates["a"].items, (1, 3))
        self.assertAlmostEqual(rates["a"].rate, 0.5)
        self.assertEqual(rates["b"].items, ())
        self.assertEqual(rates["b"].rate, 0.0)
        self.assertEqual(rates["c"].items, (2, 3))
        self.assertAlmostEqual(rates["c"].rate, 0.5)

    def test_builds_from_existing_agreement_report(self):
        report = agreement_matrix(JUDGES, CASES, RUBRIC, epsilon=0.05)
        atlas = disagreement_atlas(report)
        again = disagreement_atlas_from_report(report)

        self.assertEqual(atlas.to_dict(), again.to_dict())
        self.assertEqual(atlas.judges, report.judges)
        self.assertEqual(atlas.cases, report.cases)
        self.assertEqual(atlas.epsilon, report.epsilon)

    def test_rejects_cases_when_passing_report(self):
        report = agreement_matrix(JUDGES, CASES, RUBRIC)
        with self.assertRaises(ValueError):
            disagreement_atlas(report, CASES, RUBRIC)

    def test_requires_cases_and_rubric_for_judges(self):
        with self.assertRaises(ValueError):
            disagreement_atlas(JUDGES)
        with self.assertRaises(ValueError):
            disagreement_atlas(JUDGES, CASES)
        with self.assertRaises(ValueError):
            disagreement_atlas(JUDGES, None, RUBRIC)

    def test_unknown_ranking_rejected(self):
        report = agreement_matrix(JUDGES, CASES, RUBRIC)
        with self.assertRaises(ValueError):
            disagreement_atlas_from_report(report, ranking="nope")  # type: ignore[arg-type]

    def test_to_dict_and_tables_are_serializable_printable(self):
        atlas = _atlas()
        payload = json.loads(json.dumps(atlas.to_dict()))

        self.assertEqual(payload["ranking"], "variance")
        self.assertEqual(len(payload["items"]), 4)
        self.assertEqual(len(payload["clusters"]), 4)
        self.assertEqual(len(payload["contrarian"]), 3)

        ascii_table = atlas.table(fmt="ascii", top=2)
        md_table = atlas.table(fmt="markdown")
        summary = atlas.summary(top=2)
        markdown = atlas.to_markdown(top=2)

        self.assertIn("var", ascii_table)
        self.assertIn("|", md_table)
        self.assertIn("contrarian rates", summary)
        self.assertIn("split clusters", summary)
        self.assertIn("# Disagreement atlas", markdown)
        self.assertIn("Contrarian rates", markdown)

    def test_unanimous_panel_has_empty_splits_and_zero_contrarian(self):
        judges = [
            FixedScoreJudge("x", {"r0": 0.7, "r1": 0.4}),
            FixedScoreJudge("y", {"r0": 0.7, "r1": 0.4}),
        ]
        cases = [("p0", "r0"), ("p1", "r1")]
        atlas = disagreement_atlas(judges, cases, RUBRIC, epsilon=0.0)

        self.assertEqual(len(atlas.clusters), 1)
        self.assertEqual(atlas.clusters[0].split_pairs, ())
        self.assertEqual(atlas.clusters[0].item_indices, (0, 1))
        for entry in atlas.contrarian:
            self.assertEqual(entry.rate, 0.0)

    def test_malformed_report_scores_rejected(self):
        bad = AgreementMatrixReport(
            judges=("a", "b"),
            cases=2,
            epsilon=0.05,
            scores={"a": (0.1, 0.2)},  # missing b; a length ok but incomplete
        )
        with self.assertRaises(ValueError):
            disagreement_atlas_from_report(bad)


if __name__ == "__main__":
    unittest.main()
