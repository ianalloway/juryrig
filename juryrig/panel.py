"""Multi-judge panels with agreement scoring."""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from .judge import Judge, PairwiseJudge


@dataclass(frozen=True)
class PanelVerdict:
    """Pooled winner from a panel of pairwise judges on one A/B pair.

    `winner` is None when the panel produced no winner — either the vote was
    a dead heat, or the judges agreed the pair was a tie. Read `agreement` to
    tell those apart: a split reports 0.5, a consensus tie reports its real
    share. Reporting a coin-flip winner would hide exactly the disagreement a
    panel exists to surface.
    """

    votes: dict[str, str] = field(default_factory=dict)
    winner: Literal["A", "B"] | None = None
    agreement: float = 1.0    # share of judges backing the winner

    @property
    def deadlocked(self) -> bool:
        return self.winner is None

    @property
    def unanimous(self) -> bool:
        return self.winner is not None and self.agreement >= 1.0


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

    def compare(self, *, prompt: str, a: str, b: str, rubric: str) -> PanelVerdict:
        """Poll every judge on an A/B pair and pool the votes by majority.

        Needs a panel of pairwise judges. Scoring judges are rejected by name
        rather than silently dropped — a quietly shrinking jury would change
        the verdict without changing the agreement number.
        """
        not_pairwise = [
            j.name for j in self.judges if not isinstance(j, PairwiseJudge)
        ]
        if not_pairwise:
            raise TypeError(
                "Panel.compare() needs judges with compare(); these lack it: "
                + ", ".join(not_pairwise)
            )

        votes = {
            j.name: j.compare(prompt=prompt, a=a, b=b, rubric=rubric)
            for j in self.judges
        }
        tally = Counter(votes.values())
        (top, top_count), *rest = tally.most_common()
        if rest and rest[0][1] == top_count:
            return PanelVerdict(votes=votes, winner=None, agreement=0.5)
        if top == "tie":
            # The panel agreed, and what it agreed on was "neither". That is a
            # verdict, not a failure to reach one, so agreement stays honest.
            return PanelVerdict(
                votes=votes, winner=None, agreement=top_count / len(votes)
            )
        return PanelVerdict(
            votes=votes, winner=top, agreement=top_count / len(votes)
        )
