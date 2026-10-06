"""Regression checks for the example's experimental controls, not model quality."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from examples.evaluation_lab import (
    DATASET,
    load_dataset,
    render_markdown,
    run_experiment,
)

ROOT = Path(__file__).resolve().parents[1]


class EvaluationLabTest(unittest.TestCase):
    def test_controls_detect_the_intended_flaws_and_expose_blind_spot(self):
        result = run_experiment()
        self.assertEqual(len(result["groups"]), 3)
        ids = []
        for group in result["groups"]:
            audits = group["audits"]
            self.assertEqual(audits["baseline"]["failures"], [])
            self.assertEqual(audits["slot_first"]["failures"], ["position"])
            self.assertEqual(audits["length_bonus"]["failures"], ["verbosity"])
            self.assertEqual(audits["injection"]["failures"], ["injection"])
            self.assertIn("consistency", audits["unstable"]["failures"])
            scores = group["agreement"]["scores"]
            self.assertEqual(scores["baseline"], scores["slot_first"])
            for i, item in enumerate(group["items"]):
                ids.append(item["id"])
                if item["id"].endswith("/keyword_stuffed"):
                    self.assertEqual(scores["baseline"][i], 1.0)
        self.assertEqual(len(ids), 48)
        self.assertEqual(len(set(ids)), len(ids))

    def test_repeat_runs_reset_state_and_match_documented_output(self):
        first = run_experiment()
        self.assertEqual(first, run_experiment())
        expected = (ROOT / "examples/evaluation_expected.md").read_text()
        self.assertEqual(render_markdown(first), expected)

    def test_atlas_preserves_the_scored_items_and_needs_no_rescoring(self):
        plain = run_experiment()
        with_atlas = run_experiment(atlas=True)
        for original, enriched in zip(plain["groups"], with_atlas["groups"]):
            self.assertEqual(original["agreement"], enriched["agreement"])
            ranking = enriched["atlas"]["items"]
            self.assertEqual(sorted(i["index"] for i in ranking), list(range(16)))
            self.assertGreater(ranking[0]["variance"], 0)

    def test_dataset_retains_provenance_and_scoring_headroom(self):
        dataset = load_dataset(DATASET)
        self.assertIn("synthetic", dataset["provenance"]["status"])
        self.assertIn("No calibration labels", dataset["provenance"]["labels"])
        for group in dataset["groups"]:
            self.assertTrue(group["semantic_rubric"])
            tokens = set(group["mock_rubric"].split())
            for case in group["cases"]:
                words = {word.lower().strip(".,") for word in case["candidate"].split()}
                self.assertEqual(len(tokens & words), 3)

    def test_json_cli_is_parseable(self):
        process = subprocess.run(
            [sys.executable, "-m", "examples.evaluation_lab", "--format", "json"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(process.stdout)["settings"]["workers"], 1)


if __name__ == "__main__":
    unittest.main()
