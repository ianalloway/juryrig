"""The CLI's --json contract: schema_version, and skipped-audit reporting."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from juryrig import Judgment, audit_suite
from juryrig.cli import SCHEMA_VERSION, main, report_to_dict, warn_skipped

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASE_FILE = {
    "rubric": RUBRIC,
    "cases": [
        {
            "prompt": "How do plants make food?",
            "good": "Plants use photosynthesis: chlorophyll captures sunlight energy.",
            "weak": "Plants eat soil.",
        }
    ],
}
LABELS = {"scores": [0.9, 0.1], "labels": [1, 0], "bins": 2}


class ScoreOnlyJudge:
    """judge() but no compare() — the position audit cannot run."""

    name = "score-only"

    def judge(self, *, prompt, response, rubric):
        return Judgment(score=0.5)


SUBCOMMANDS = ("agree", "atlas", "calibrate")


def run_cli(payload, *args):
    """Run the CLI over `payload`, written to a temp file.

    `audit` is the bare default, so its file path comes first; the named
    subcommands take theirs after the subcommand.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "in.json"
        path.write_text(json.dumps(payload))
        if args and args[0] in SUBCOMMANDS:
            argv = [args[0], str(path), *args[1:]]
        else:
            argv = [str(path), *args]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()


class SchemaVersionTest(unittest.TestCase):
    def test_audit_json_is_stamped(self):
        _, out, _ = run_cli(CASE_FILE, "--json")
        payload = json.loads(out)

        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["report"], "audit")

    def test_calibrate_json_is_stamped(self):
        _, out, _ = run_cli(LABELS, "calibrate", "--json")
        payload = json.loads(out)

        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["report"], "calibrate")

    def test_every_subcommand_identifies_itself(self):
        for args, expected in (
            (("--json",), "audit"),
            (("agree", "--json"), "agree"),
            (("atlas", "--json"), "atlas"),
        ):
            with self.subTest(report=expected):
                _, out, _ = run_cli(CASE_FILE, *args)
                payload = json.loads(out)
                self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
                self.assertEqual(payload["report"], expected)

    def test_stamping_does_not_shadow_payload_keys(self):
        """The wrapper must not overwrite a report's own fields."""
        _, out, _ = run_cli(CASE_FILE, "--json")
        payload = json.loads(out)

        self.assertIn("judge", payload)
        self.assertIn("audits", payload)
        self.assertEqual(payload["judge"], "mock")


class SkippedAuditTest(unittest.TestCase):
    def report(self):
        return audit_suite(
            ScoreOnlyJudge(), [("q", "photosynthesis", "soil")], RUBRIC
        )

    def test_reason_travels_with_the_report(self):
        report = self.report()

        self.assertEqual(report.skipped, ("position",))
        self.assertIn("position", report.skipped_reasons)
        self.assertIn("compare()", report.skipped_reasons["position"])

    def test_a_skipped_audit_is_not_a_pass(self):
        """The gap this closes: a clean verdict hiding an audit that never ran."""
        report = self.report()

        self.assertFalse(report.flagged)          # looks clean ...
        self.assertTrue(report.skipped)           # ... but was not fully audited
        self.assertNotIn("position", report.failures)

    def test_a_pairwise_judge_skips_nothing(self):
        from juryrig import MockJudge

        report = audit_suite(MockJudge(), [("q", "a", "b")], RUBRIC)

        self.assertEqual(report.skipped, ())
        self.assertEqual(report.skipped_reasons, {})

    def test_json_carries_the_reasons(self):
        payload = report_to_dict(self.report())

        self.assertEqual(payload["skipped"], ["position"])
        self.assertIn("position", payload["skipped_reasons"])

    def test_warning_goes_to_stderr_not_stdout(self):
        """--json output must stay machine-readable when a warning fires."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            warn_skipped(self.report())

        self.assertEqual(out.getvalue(), "")
        self.assertIn("position audit skipped", err.getvalue())
        self.assertIn("not fully audited", err.getvalue())

    def test_no_warning_when_nothing_was_skipped(self):
        from juryrig import MockJudge

        err = io.StringIO()
        with redirect_stderr(err):
            warn_skipped(audit_suite(MockJudge(), [("q", "a", "b")], RUBRIC))

        self.assertEqual(err.getvalue(), "")

    def test_cli_stays_silent_for_a_fully_audited_judge(self):
        _, _, err = run_cli(CASE_FILE)

        self.assertEqual(err, "")


class DocumentedContractTest(unittest.TestCase):
    """Keep docs/report-schema.md honest about what the CLI emits."""

    DOC = Path(__file__).resolve().parents[1] / "docs" / "report-schema.md"

    @unittest.skipUnless(DOC.is_file(), "running outside the source tree")
    def test_doc_states_the_current_version(self):
        self.assertIn(f"Currently `{SCHEMA_VERSION}`", self.DOC.read_text())

    @unittest.skipUnless(DOC.is_file(), "running outside the source tree")
    def test_doc_mentions_every_report_name(self):
        text = self.DOC.read_text()
        for name in ("audit", "agree", "atlas", "calibrate"):
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", text)


if __name__ == "__main__":
    unittest.main()
