"""Run every audit against one judge and get a single verdict.

The individual audits in `audits` each answer one question. This runs the
whole battery and pools the answers, so gating a pipeline stays one `if`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .audits import (
    DEFAULT_THRESHOLDS,
    ConsistencyReport,
    PositionBiasReport,
    PromptInjectionReport,
    Thresholds,
    VerbosityBiasReport,
    position_bias,
    prompt_injection_bias,
    self_consistency,
    verbosity_bias,
)
from .judge import Judge, PairwiseJudge


@dataclass(frozen=True)
class AuditSuiteReport:
    """Every audit's verdict on one judge.

    `position` is None when the judge has no `compare()` — a single-response
    judge simply cannot be audited for position bias, which is different from
    passing that audit.
    """

    judge: str
    verbosity: VerbosityBiasReport
    injection: PromptInjectionReport
    consistency: ConsistencyReport      # the least stable case, not the first
    position: PositionBiasReport | None = None
    consistency_cases: int = 1          # how many cases the above was worst of

    @property
    def failures(self) -> tuple[str, ...]:
        """Names of the audits that flagged, in run order."""
        named = (
            ("position", self.position),
            ("verbosity", self.verbosity),
            ("injection", self.injection),
            ("consistency", self.consistency),
        )
        return tuple(name for name, r in named if r is not None and r.flagged)

    @property
    def skipped(self) -> tuple[str, ...]:
        """Audits that could not run against this judge."""
        return () if self.position is not None else ("position",)

    @property
    def flagged(self) -> bool:
        """True if any audit flagged. Trust the judge only when this is False."""
        return bool(self.failures)

    def summary(self) -> str:
        """Human-readable one-line-per-audit report."""
        lines = [f"judge: {self.judge}"]
        if self.position is None:
            lines.append("position    skipped (judge has no compare())")
        else:
            lines.append(
                "position    "
                f"flip_rate={self.position.flip_rate:.0%} "
                f"first_slot_wins={self.position.first_slot_wins:.0%} "
                f"ties={self.position.ties} "
                f"flagged={self.position.flagged}"
            )
        lines.append(
            "verbosity   "
            f"mean_delta={self.verbosity.mean_delta:+.3f} "
            f"max_delta={self.verbosity.max_delta:+.3f} "
            f"flagged={self.verbosity.flagged}"
        )
        lines.append(
            "injection   "
            f"mean_delta={self.injection.mean_delta:+.3f} "
            f"max_delta={self.injection.max_delta:+.3f} "
            f"flagged={self.injection.flagged}"
        )
        lines.append(
            "consistency "
            f"worst_spread={self.consistency.spread:.3f} "
            f"of={self.consistency_cases} "
            f"flagged={self.consistency.flagged}"
        )
        verdict = (
            f"FLAGGED by: {', '.join(self.failures)}"
            if self.flagged
            else "PASSED all audits"
        )
        lines.append(verdict)
        return "\n".join(lines)


def audit_suite(
    judge: Judge,
    cases: list[tuple[str, str, str]],
    rubric: str,
    *,
    runs: int = 5,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    max_workers: int = 1,
) -> AuditSuiteReport:
    """Run the full battery against `judge`.

    Each case is a (prompt, good_response, weak_response) triple, which is
    what the audits between them need: the pair feeds the position-bias
    comparison, the good response is what gets padded to detect verbosity
    bias, and the weak one carries the injection payload — a judge that
    already scores a response highly leaves no headroom to measure a lift.
    """
    if not cases:
        raise ValueError("audit_suite needs at least one case.")

    good_pairs = [(prompt, good) for prompt, good, _ in cases]
    weak_pairs = [(prompt, weak) for prompt, _, weak in cases]

    position = (
        position_bias(
            judge, cases, rubric, thresholds=thresholds, max_workers=max_workers
        )
        if isinstance(judge, PairwiseJudge)
        else None
    )
    # Every case, not just the first: a judge can be rock-steady on one input
    # and erratic on the next, and checking one would call that stable. The
    # worst case is the one that matters, so keep it.
    per_case = [
        self_consistency(
            judge,
            prompt=prompt,
            response=response,
            rubric=rubric,
            runs=runs,
            thresholds=thresholds,
            max_workers=max_workers,
        )
        for prompt, response, _ in cases
    ]
    return AuditSuiteReport(
        judge=getattr(judge, "name", judge.__class__.__name__),
        position=position,
        verbosity=verbosity_bias(
            judge, good_pairs, rubric, thresholds=thresholds, max_workers=max_workers
        ),
        injection=prompt_injection_bias(
            judge, weak_pairs, rubric, thresholds=thresholds, max_workers=max_workers
        ),
        consistency=max(per_case, key=lambda report: report.spread),
        consistency_cases=len(per_case),
    )
