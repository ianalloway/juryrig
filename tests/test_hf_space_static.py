"""Regression checks for the browser Space's JSON bridge."""
import json
import runpy
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[1] / "hf-space-static" / "space.py"
_SPACE = runpy.run_path(str(_SOURCE))


def call(name, *args):
    reply = json.loads(_SPACE["api"](name, json.dumps(args)))
    assert reply["ok"], reply
    return reply["result"]


def test_demo_explains_a_real_mock_judge_swap():
    judges, _, cases, example = call("run_demo")
    original, swapped = example["choices"]
    assert len(judges) == 5
    assert cases == 3
    assert original[1:3] == swapped[1:3][::-1]
    assert original[-1] != swapped[-1]


def test_position_export_distinguishes_slot_changes_from_winner_changes():
    sample = (
        "case_id,verdict_original,verdict_swapped\n"
        "good,A,B\nchange,A,A\ntie,tie,tie\n"
    )
    _, _, count, changes = call("on_position", sample, 0.2, 0.2)
    assert count == 3
    assert changes == [["change", "A", "A", "Response X", "Response Y"]]


def test_other_reports_return_sample_counts():
    _, _, changes, count = call(
        "on_verbosity", _SPACE["EXAMPLE_VERBOSITY"], 1, 0.05, 0.15
    )
    assert count == len(changes) > 0
    _, bins, count = call("on_calibration", _SPACE["EXAMPLE_CALIBRATION"], 5)
    assert count == sum(row[1] for row in bins) > 0
    _, pairs, atlas, count = call("on_agreement", _SPACE["EXAMPLE_AGREEMENT"], 1, 0.05)
    assert count > 0 and pairs and atlas
