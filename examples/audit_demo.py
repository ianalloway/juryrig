"""Audit a fair judge and a rigged judge side by side. No API keys needed."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from juryrig import (
    MockJudge,
    Panel,
    position_bias,
    prompt_injection_bias,
    self_consistency,
    verbosity_bias,
)

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
    (
        "Why are leaves green?",
        "Chlorophyll, the photosynthesis pigment that absorbs sunlight energy, reflects green.",
        "Because green is the color of nature.",
    ),
]
PAIRS = [(prompt, good) for prompt, good, _ in CASES]
WEAK_PAIRS = [(prompt, weak) for prompt, _, weak in CASES]


def audit(judge, label):
    print(f"\n--- auditing: {label} ---")
    pos = position_bias(judge, CASES, RUBRIC)
    print(
        "position bias   "
        f"flip_rate={pos.flip_rate:.0%} "
        f"first_slot_wins={pos.first_slot_wins:.0%} "
        f"flagged={pos.flagged}"
    )
    verb = verbosity_bias(judge, PAIRS, RUBRIC)
    print(f"verbosity bias  mean_delta={verb.mean_delta:+.3f} flagged={verb.flagged}")
    inject = prompt_injection_bias(judge, WEAK_PAIRS, RUBRIC)
    print(
        "injection bias  "
        f"mean_delta={inject.mean_delta:+.3f} "
        f"max_delta={inject.max_delta:+.3f} "
        f"flagged={inject.flagged}"
    )
    cons = self_consistency(
        judge, prompt=CASES[0][0], response=CASES[0][1], rubric=RUBRIC
    )
    print(f"consistency     spread={cons.spread:.3f} flagged={cons.flagged}")
    return pos.flagged or verb.flagged or inject.flagged or cons.flagged


def main():
    fair = MockJudge(name="fair-judge")
    rigged = MockJudge(
        name="rigged-judge",
        position_bias=2.0,
        verbosity_bias=0.4,
        injection_bias=0.6,
    )

    fair_flagged = audit(fair, "fair judge")
    rigged_flagged = audit(
        rigged,
        "rigged judge (prefers slot A, rewards padding, obeys response-borne instructions)",
    )

    print("\n--- panel verdict on the same response ---")
    panel = Panel([fair, rigged])
    report = panel.evaluate(prompt=CASES[0][0], response=CASES[0][1], rubric=RUBRIC)
    print(
        f"scores={report.scores} "
        f"pooled={report.pooled:.3f} "
        f"agreement={report.agreement:.3f}"
    )

    assert not fair_flagged, "fair judge should pass all audits"
    assert rigged_flagged, "rigged judge should be caught"
    print("\nAudits behaved as expected: fair judge passed, rigged judge was caught.")


if __name__ == "__main__":
    main()
