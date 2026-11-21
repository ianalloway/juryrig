"""The pytest plugin, exercised by running pytest in a subprocess.

A subprocess tests the real integration — plugin loading, fixtures, markers
and the failure text — and works whether this file is collected by unittest
or by pytest. Skipped where pytest is not installed, so the unittest suite
still passes on a bare interpreter.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from importlib.metadata import entry_points
from pathlib import Path

try:
    import pytest  # noqa: F401
    HAVE_PYTEST = True
except ImportError:
    HAVE_PYTEST = False

REPO = Path(__file__).resolve().parents[1]


def plugin_args() -> list[str]:
    """Load the plugin explicitly only when the entry point will not.

    From a source tree juryrig is not installed, so pytest needs -p. Once it
    IS installed the pytest11 entry point already registers the module, and
    passing -p would register it a second time under another name, which
    pytest rejects outright.
    """
    registered = any(
        ep.module == "juryrig.pytest_plugin"
        for ep in entry_points(group="pytest11")
    )
    return [] if registered else ["-p", "juryrig.pytest_plugin"]

PREAMBLE = '''
    import pytest
    from juryrig import Judgment, MockJudge

    RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
    CASES = [("q1", "photosynthesis chlorophyll sunlight energy", "soil")]

    class ScoreOnly:
        name = "score-only"
        def judge(self, *, prompt, response, rubric):
            return Judgment(score=0.5)
'''


@unittest.skipUnless(HAVE_PYTEST, "pytest is not installed")
class PluginTest(unittest.TestCase):
    def run_pytest(self, body: str):
        # Both blocks use the same indent, so dedent strips it from the
        # whole file; prepending an unindented line would defeat that.
        source = textwrap.dedent(PREAMBLE + body)
        with tempfile.TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test_generated.py"
            test_file.write_text(source)
            completed = subprocess.run(
                [
                    sys.executable, "-m", "pytest", "-q",
                    *plugin_args(), str(test_file),
                ],
                capture_output=True, text=True, cwd=tmp,
                env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"},
                timeout=120,
            )
        return completed.returncode, completed.stdout + completed.stderr

    def test_fair_judge_passes(self):
        code, out = self.run_pytest('''
    def test_it(assert_judge_clean):
        assert_judge_clean(MockJudge(), CASES, RUBRIC)
''')

        self.assertEqual(code, 0, out)

    def test_rigged_judge_fails_and_names_the_audit(self):
        code, out = self.run_pytest('''
    def test_it(assert_judge_clean):
        assert_judge_clean(MockJudge(injection_bias=0.6), CASES, RUBRIC)
''')

        self.assertNotEqual(code, 0)
        # A red test should say what is wrong with the judge, not just that
        # something is.
        self.assertIn("flagged by: injection", out)
        self.assertIn("mean_delta", out)

    def test_marker_overrides_thresholds(self):
        code, out = self.run_pytest('''
    @pytest.mark.juryrig(injection_mean_delta=0.9, injection_max_delta=0.9)
    def test_it(assert_judge_clean):
        assert_judge_clean(MockJudge(injection_bias=0.6), CASES, RUBRIC)
''')

        self.assertEqual(code, 0, out)

    def test_unknown_threshold_in_marker_is_reported(self):
        """A typo must fail loudly, not leave the strict default in force."""
        code, out = self.run_pytest('''
    @pytest.mark.juryrig(injection_men_delta=0.9)
    def test_it(assert_judge_clean):
        assert_judge_clean(MockJudge(), CASES, RUBRIC)
''')

        self.assertNotEqual(code, 0)
        self.assertIn("unknown threshold", out)
        self.assertIn("Valid names", out)

    def test_skipped_audit_passes_by_default(self):
        code, out = self.run_pytest('''
    def test_it(assert_judge_clean):
        assert_judge_clean(ScoreOnly(), CASES, RUBRIC)
''')

        self.assertEqual(code, 0, out)

    def test_require_full_fails_on_a_skipped_audit(self):
        code, out = self.run_pytest('''
    def test_it(assert_judge_clean):
        assert_judge_clean(ScoreOnly(), CASES, RUBRIC, require_full=True)
''')

        self.assertNotEqual(code, 0)
        self.assertIn("did not run", out)
        self.assertIn("position", out)

    def test_judge_audit_fixture_returns_the_report(self):
        code, out = self.run_pytest('''
    def test_it(judge_audit):
        report = judge_audit(MockJudge(injection_bias=0.6), CASES, RUBRIC)
        assert report.flagged                 # returns, does not assert
        assert "injection" in report.failures
''')

        self.assertEqual(code, 0, out)

    def test_marker_is_registered(self):
        """An unregistered marker warns, and -W error would fail the run."""
        code, out = self.run_pytest('''
    def test_it(assert_judge_clean):
        assert_judge_clean(MockJudge(), CASES, RUBRIC)
''')

        self.assertEqual(code, 0, out)
        self.assertNotIn("PytestUnknownMarkWarning", out)


if __name__ == "__main__":
    unittest.main()
