"""`juryrig report` — one page combining whatever the case file supports."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from juryrig.cli import main
from juryrig.onepager import OnePager, Section

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [
    {
        "prompt": "How do plants make food?",
        "good": "Plants use photosynthesis: chlorophyll captures sunlight energy.",
        "weak": "Plants eat soil.",
    },
    {
        "prompt": "Explain plant energy.",
        "good": "Through photosynthesis, sunlight energy uses chlorophyll.",
        "weak": "It just happens.",
    },
]
MINIMAL = {"rubric": RUBRIC, "cases": CASES}
FULL = {
    **MINIMAL,
    "rubrics": [RUBRIC, "The response should explain photosynthesis using chlorophyll"],
    "scores": [0.95, 0.9, 0.3, 0.1],
    "labels": [1, 0, 0, 0],
    "bins": 2,
}


def run_report(payload, *args, suffix=".json"):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"cases{suffix}"
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload)
        )
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["report", str(path), *args])
        return code, out.getvalue(), err.getvalue()


class RendererTest(unittest.TestCase):
    def page(self):
        return OnePager(
            judge="demo",
            sections=[
                Section("Clean thing", flagged=False, lines=["all good"]),
                Section("Broken thing", flagged=True, lines=["bad=1"], note="why"),
            ],
            omitted={"Skipped thing": "no data for it"},
        )

    def test_flagged_when_any_section_is(self):
        page = self.page()

        self.assertTrue(page.flagged)
        self.assertEqual(page.failures, ("Broken thing",))

    def test_clean_page_is_not_flagged(self):
        page = OnePager(judge="d", sections=[Section("ok", False, ["x"])])

        self.assertFalse(page.flagged)
        self.assertEqual(page.failures, ())

    def test_markdown_lists_omissions_as_not_passing(self):
        text = self.page().to_markdown()

        self.assertIn("## Omitted", text)
        self.assertIn("not a passing one", text)
        self.assertIn("no data for it", text)

    def test_html_is_self_contained(self):
        text = self.page().to_html()

        self.assertTrue(text.startswith("<!doctype html>"))
        self.assertIn("<style>", text)
        # No third-party requests, same as the rest of the library.
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)

    def test_html_escapes_case_file_content(self):
        """A shared report must not be able to carry injected script."""
        page = OnePager(
            judge="<script>alert(1)</script>",
            sections=[
                Section("<img src=x onerror=alert(1)>", False, ["<b>raw</b>"])
            ],
            omitted={"<i>x</i>": "<u>y</u>"},
        )
        text = page.to_html()

        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertNotIn("<img src=x", text)
        self.assertNotIn("<b>raw</b>", text)
        self.assertIn("&lt;script&gt;", text)


class CliTest(unittest.TestCase):
    def test_minimal_file_runs_the_suite_and_omits_the_rest(self):
        code, out, _ = run_report(MINIMAL)

        self.assertEqual(code, 0)
        self.assertIn("Bias and consistency suite", out)
        self.assertIn("## Omitted", out)
        self.assertIn("Rubric sensitivity", out)
        self.assertIn("Calibration", out)

    def test_full_file_includes_every_section(self):
        code, out, _ = run_report(FULL)

        self.assertEqual(code, 1)   # the labels are deliberately miscalibrated
        self.assertIn("Rubric sensitivity", out)
        self.assertIn("expected_calibration_error", out)
        self.assertIn("Cost", out)
        self.assertNotIn("## Omitted", out)

    def test_html_format(self):
        _, out, _ = run_report(FULL, "--fmt", "html")

        self.assertTrue(out.startswith("<!doctype html>"))
        self.assertIn("juryrig report", out)

    def test_cost_section_always_present(self):
        _, out, _ = run_report(MINIMAL)

        self.assertIn("Cost", out)
        self.assertIn("calls=", out)

    def test_jsonl_input_omits_the_extra_sections(self):
        # A JSONL file has no single object to read "rubrics"/"labels" from.
        records = [{"rubric": RUBRIC}, *CASES]
        code, out, _ = run_report(
            "\n".join(map(json.dumps, records)), suffix=".jsonl"
        )

        self.assertEqual(code, 0)
        self.assertIn("Bias and consistency suite", out)
        self.assertIn("## Omitted", out)

    def test_bad_input_exits_two(self):
        for payload in ("{not json", {}, {"rubric": RUBRIC, "cases": []}):
            with self.subTest(payload=payload):
                code, _, err = run_report(payload)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("juryrig:"), err)

    def test_rejects_bad_runs_and_workers(self):
        for flag in ("--runs", "--workers"):
            with self.subTest(flag=flag):
                code, _, err = run_report(MINIMAL, flag, "0")
                self.assertEqual(code, 2)
                self.assertIn(flag, err)


if __name__ == "__main__":
    unittest.main()
