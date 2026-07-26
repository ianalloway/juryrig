import unittest

from juryrig import MockJudge, audit_suite

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


class SingleResponseJudge:
    """A judge with judge() but no compare() — position bias is unmeasurable."""

    name = "single"

    def __init__(self, inner):
        self._inner = inner

    def judge(self, *, prompt, response, rubric):
        return self._inner.judge(prompt=prompt, response=response, rubric=rubric)


class AuditSuiteTest(unittest.TestCase):
    def test_fair_judge_passes_every_audit(self):
        report = audit_suite(MockJudge(name="fair"), CASES, RUBRIC)

        self.assertEqual(report.judge, "fair")
        self.assertEqual(report.failures, ())
        self.assertFalse(report.flagged)
        self.assertIsNotNone(report.position)

    def test_rigged_judge_flagged_by_every_audit(self):
        rigged = MockJudge(
            name="rigged",
            position_bias=2.0,
            verbosity_bias=0.4,
            injection_bias=0.6,
        )
        report = audit_suite(rigged, CASES, RUBRIC)

        self.assertTrue(report.flagged)
        self.assertEqual(
            set(report.failures), {"position", "verbosity", "injection"}
        )

    def test_each_flaw_is_attributed_to_its_own_audit(self):
        windbag = audit_suite(MockJudge(verbosity_bias=0.4), CASES, RUBRIC)
        self.assertEqual(windbag.failures, ("verbosity",))

        gullible = audit_suite(MockJudge(injection_bias=0.6), CASES, RUBRIC)
        self.assertEqual(gullible.failures, ("injection",))

    def test_position_audit_skipped_without_compare(self):
        report = audit_suite(SingleResponseJudge(MockJudge()), CASES, RUBRIC)

        self.assertIsNone(report.position)
        self.assertEqual(report.skipped, ("position",))
        self.assertNotIn("position", report.failures)
        self.assertIn("skipped", report.summary())

    def test_skipped_position_audit_does_not_mask_other_flaws(self):
        report = audit_suite(
            SingleResponseJudge(MockJudge(injection_bias=0.6)), CASES, RUBRIC
        )

        self.assertTrue(report.flagged)
        self.assertEqual(report.failures, ("injection",))

    def test_summary_reports_verdict(self):
        self.assertIn("PASSED", audit_suite(MockJudge(), CASES, RUBRIC).summary())
        rigged = audit_suite(MockJudge(injection_bias=0.6), CASES, RUBRIC)
        self.assertIn("FLAGGED", rigged.summary())

    def test_rejects_empty_cases(self):
        with self.assertRaises(ValueError):
            audit_suite(MockJudge(), [], RUBRIC)


if __name__ == "__main__":
    unittest.main()
