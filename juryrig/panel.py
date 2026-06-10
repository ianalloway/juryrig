"""Multi-judge panels with agreement scoring."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .judge import Judge


@dataclass(frozen=True)
class PanelReport:
    """Pooled verdict from a panel of judges on one response."""

    scores: dict[str, float] = field(default_factory=dict)
    pooled: float = 0.0
    spread: float = 0.0       # max - min individual score
    agreement: float = 1.0    # 1 - mean pairwise |difference|; 1.0 = unanimous

    @property
    def unanimous(self) -> bool:
        return self.spread < 1e-9


class Panel:
    """A jury of judges. Pools scores and reports how much they disagree.

    A high pooled score with low agreement is a warning sign: your
    evaluation depends on which judge you happened to pick.
    """

    def __init__(self, judges: list[Judge], pool: str = "mean") -> None:
        if not judges:
            raise ValueError("Panel needs at least one judge.")
        if pool not in {"mean", "median", "min"}:
            raise ValueError("pool must be 'mean', 'median', or 'min'.")
        names = [j.name for j in judges]
        if len(set(names)) != len(names):
            raise ValueError("Judge names must be unique within a panel.")
        self.judges = judges
        self.pool = pool

    def evaluate(self, *, prompt: str, response: str, rubric: str) -> PanelReport:
        scores = {
            j.name: j.judge(prompt=prompt, response=response, rubric=rubric).score
            for j in self.judges
        }
        values = list(scores.values())
        pooled = {
            "mean": statistics.fmean,
            "median": statistics.median,
            "min": min,
        }[self.pool](values)

        if len(values) < 2:
            return PanelReport(scores=scores, pooled=pooled, spread=0.0, agreement=1.0)

        diffs = [
            abs(x - y)
            for i, x in enumerate(values)
            for y in values[i + 1:]
        ]
        return PanelReport(
            scores=scores,
            pooled=pooled,
            spread=max(values) - min(values),
            agreement=1.0 - statistics.fmean(diffs),
        )
