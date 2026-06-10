import unittest

from juryrig import MockJudge, Panel

RUBRIC = "mention photosynthesis chlorophyll sunlight energy"
RESPONSE = "Photosynthesis uses chlorophyll to turn sunlight into energy."


class PanelTest(unittest.TestCase):
    def test_unanimous_identical_judges(self):
        panel = Panel([MockJudge(name="a"), MockJudge(name="b")])
        report = panel.evaluate(prompt="q", response=RESPONSE, rubric=RUBRIC)
        self.assertTrue(report.unanimous)
        self.assertEqual(report.agreement, 1.0)

    def test_disagreement_lowers_agreement(self):
        panel = Panel([MockJudge(name="fair"), MockJudge(name="windbag", verbosity_bias=0.9)])
        report = panel.evaluate(prompt="q", response=RESPONSE, rubric=RUBRIC)
        self.assertLess(report.agreement, 1.0)
        self.assertGreater(report.spread, 0.0)

    def test_pooling_modes(self):
        judges = [MockJudge(name="fair"), MockJudge(name="windbag", verbosity_bias=0.9)]
        mean_pool = Panel(judges, pool="mean").evaluate(prompt="q", response=RESPONSE, rubric=RUBRIC)
        min_pool = Panel(judges, pool="min").evaluate(prompt="q", response=RESPONSE, rubric=RUBRIC)
        self.assertLessEqual(min_pool.pooled, mean_pool.pooled)

    def test_rejects_duplicate_names_and_empty(self):
        with self.assertRaises(ValueError):
            Panel([])
        with self.assertRaises(ValueError):
            Panel([MockJudge(name="x"), MockJudge(name="x")])


if __name__ == "__main__":
    unittest.main()
