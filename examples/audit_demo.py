"""Audit a fair judge and a rigged judge side by side. No API keys needed."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from juryrig import MockJudge, Panel, audit_suite

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


def main():
    fair = MockJudge(name="fair-judge")
    rigged = MockJudge(
        name="rigged-judge",
        position_bias=2.0,
        verbosity_bias=0.4,
        injection_bias=0.6,
    )

    print("--- auditing: fair judge ---")
    fair_report = audit_suite(fair, CASES, RUBRIC)
    print(fair_report.summary())

    print(
        "\n--- auditing: rigged judge "
        "(prefers slot A, rewards padding, obeys response-borne instructions) ---"
    )
    rigged_report = audit_suite(rigged, CASES, RUBRIC)
    print(rigged_report.summary())

    print("\n--- panel verdict on the same response ---")
    panel = Panel([fair, rigged])
    report = panel.evaluate(prompt=CASES[0][0], response=CASES[0][1], rubric=RUBRIC)
    print(
        f"scores={report.scores} "
        f"pooled={report.pooled:.3f} "
        f"agreement={report.agreement:.3f}"
    )

    assert not fair_report.flagged, "fair judge should pass all audits"
    assert rigged_report.flagged, "rigged judge should be caught"
    print("\nAudits behaved as expected: fair judge passed, rigged judge was caught.")


if __name__ == "__main__":
    main()
