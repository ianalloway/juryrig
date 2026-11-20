"""pytest plugin: fail a test when a judge crosses its thresholds.

Loaded automatically once juryrig is installed, via the `pytest11` entry
point. pytest is a test-time dependency only — nothing in the library
imports this module, so `import juryrig` still needs no third-party package.

    def test_our_judge_is_fair(assert_judge_clean):
        assert_judge_clean(our_judge, cases, rubric)

The failure message names which audits flagged and the numbers behind them,
so a red test says what is wrong with the judge rather than just that
something is.
"""
from __future__ import annotations

import pytest

from .audits import DEFAULT_THRESHOLDS, Thresholds
from .suite import audit_suite


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "juryrig(**thresholds): override juryrig audit thresholds for a test, "
        "e.g. @pytest.mark.juryrig(verbosity_mean_delta=0.1)",
    )


@pytest.fixture
def juryrig_thresholds(request) -> Thresholds:
    """Thresholds for this test, from a `juryrig` marker if it carries any."""
    marker = request.node.get_closest_marker("juryrig")
    if marker is None or not marker.kwargs:
        return DEFAULT_THRESHOLDS
    try:
        return Thresholds(**marker.kwargs)
    except TypeError as exc:
        # A typo'd threshold would otherwise be silently ignored, leaving the
        # strict default in force while the test claims to have loosened it.
        valid = ", ".join(sorted(Thresholds.__dataclass_fields__))
        pytest.fail(
            f"@pytest.mark.juryrig got an unknown threshold: {exc}. "
            f"Valid names: {valid}"
        )


@pytest.fixture
def judge_audit(juryrig_thresholds):
    """Run the audit suite, returning the report. Does not assert."""

    def run(judge, cases, rubric, **kwargs):
        kwargs.setdefault("thresholds", juryrig_thresholds)
        return audit_suite(judge, cases, rubric, **kwargs)

    return run


@pytest.fixture
def assert_judge_clean(judge_audit):
    """Audit a judge and fail the test if anything flagged.

    Pass `require_full=True` to also fail when an audit could not run. That
    is off by default — a skipped audit is a coverage gap, not a defect — but
    a test asserting a judge is fair may want to insist the whole battery
    actually ran.
    """

    def check(judge, cases, rubric, *, require_full=False, **kwargs):
        report = judge_audit(judge, cases, rubric, **kwargs)
        problems = []
        if report.flagged:
            problems.append(
                f"flagged by: {', '.join(report.failures)}\n{report.summary()}"
            )
        if require_full and report.skipped:
            problems.append(
                "audits that did not run: "
                + "; ".join(
                    f"{name} ({why})"
                    for name, why in report.skipped_reasons.items()
                )
            )
        if problems:
            pytest.fail(
                f"judge {report.judge!r} is not clean:\n\n"
                + "\n\n".join(problems),
                pytrace=False,
            )
        return report

    return check
