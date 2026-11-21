"""Count what an audit costs: calls and wall-clock time.

Wrap a judge before auditing it, then read the usage afterwards:

    from juryrig import audit_suite, metered

    judge = metered(my_judge)
    report = audit_suite(judge, cases, rubric)
    print(judge.usage().summary())

Nothing here talks to a billing API. It counts calls and measures elapsed
time, which is what you need to estimate the cost of a run on a paid
provider before pointing it at a large case set.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .judge import Judge, Judgment, PairwiseJudge, Verdict


@dataclass(frozen=True)
class UsageReport:
    """How many calls an audit made, and how long they took."""

    judge_calls: int
    compare_calls: int
    seconds: float

    @property
    def calls(self) -> int:
        return self.judge_calls + self.compare_calls

    @property
    def seconds_per_call(self) -> float:
        return self.seconds / self.calls if self.calls else 0.0

    def projected_seconds(self, calls: int) -> float:
        """Rough wall-clock estimate for `calls`, at the rate observed so far.

        Serial and only as good as the sample: a handful of fast calls will
        under-predict a long run against a rate-limited API.
        """
        if calls < 0:
            raise ValueError("calls must be non-negative.")
        return self.seconds_per_call * calls

    def summary(self) -> str:
        return (
            f"calls={self.calls} (judge={self.judge_calls} "
            f"compare={self.compare_calls})  "
            f"seconds={self.seconds:.3f}  "
            f"per_call={self.seconds_per_call:.4f}"
        )


class _Counter:
    """Shared tally. Audits can run in parallel, so the counters need a lock."""

    def __init__(self, clock) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self.judge_calls = 0
        self.compare_calls = 0
        self.seconds = 0.0

    def record(self, kind: str, elapsed: float) -> None:
        with self._lock:
            if kind == "judge":
                self.judge_calls += 1
            else:
                self.compare_calls += 1
            # Summed per call, so under parallelism this is total work done,
            # not elapsed wall time for the run as a whole.
            self.seconds += elapsed

    def report(self) -> UsageReport:
        with self._lock:
            return UsageReport(
                judge_calls=self.judge_calls,
                compare_calls=self.compare_calls,
                seconds=self.seconds,
            )


class MeteredJudge:
    """A judge that counts its own `judge()` calls."""

    def __init__(self, judge: Judge, clock=time.monotonic) -> None:
        self._judge = judge
        self._clock = clock
        self._counter = _Counter(clock)
        self.name = getattr(judge, "name", judge.__class__.__name__)

    @property
    def inner(self) -> Judge:
        return self._judge

    def usage(self) -> UsageReport:
        return self._counter.report()

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        started = self._clock()
        try:
            return self._judge.judge(prompt=prompt, response=response, rubric=rubric)
        finally:
            # Charged even when the call raises: a failed request still costs
            # time, and on a paid API it may still have been billed.
            self._counter.record("judge", self._clock() - started)


class MeteredPairwiseJudge(MeteredJudge):
    """A metered judge that also counts `compare()` calls."""

    def compare(self, *, prompt: str, a: str, b: str, rubric: str) -> Verdict:
        started = self._clock()
        try:
            return self._judge.compare(prompt=prompt, a=a, b=b, rubric=rubric)
        finally:
            self._counter.record("compare", self._clock() - started)


def metered(judge: Judge, clock=time.monotonic) -> MeteredJudge:
    """Wrap `judge` so it counts its calls, preserving what it can do.

    The wrapper only grows a `compare()` when the judge it wraps has one.
    That matters: `audit_suite()` decides whether to run the position audit
    by checking for `compare()`, so a wrapper that always had one would make
    a score-only judge look pairwise and quietly undo the skipped-audit
    reporting.
    """
    if isinstance(judge, PairwiseJudge):
        return MeteredPairwiseJudge(judge, clock)
    return MeteredJudge(judge, clock)
