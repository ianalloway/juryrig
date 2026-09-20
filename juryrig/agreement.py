"""Pairwise judge agreement / concordance matrix.

Score the same items with N judges (or N prompt variants wrapped as
judges) and measure how often they agree. A high pooled panel score with
low pairwise kappa is a warning: the verdict depends on which judge you
happened to pick.

Zero third-party deps — Cohen's kappa is a few lines of arithmetic.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence, TypeVar

from .judge import Judge

_T = TypeVar("_T")
_R = TypeVar("_R")


def _map(fn: Callable[[_T], _R], items: Iterable[_T], max_workers: int) -> list[_R]:
    """Apply `fn` to every item, returning results in input order."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1.")
    if max_workers == 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(fn, items))


def cohen_kappa(labels_a: Sequence[object], labels_b: Sequence[object]) -> float:
    """Cohen's kappa for two raters on the same items.

    Returns 1.0 for perfect agreement, ~0 for chance-level, and negative
    when agreement is worse than chance. With nothing to compare (empty
    inputs, or a single category that both raters always emit so Pe == 1)
    returns 1.0 when they never disagree and 0.0 otherwise — there is no
    chance baseline left to estimate.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("label sequences must be the same length.")
    n = len(labels_a)
    if n == 0:
        return 1.0

    categories = sorted({*labels_a, *labels_b}, key=lambda c: (str(type(c)), str(c)))
    agree = sum(a == b for a, b in zip(labels_a, labels_b))
    po = agree / n

    # Marginal proportions per category for each rater.
    pa = {c: sum(x == c for x in labels_a) / n for c in categories}
    pb = {c: sum(x == c for x in labels_b) / n for c in categories}
    pe = sum(pa[c] * pb[c] for c in categories)

    if pe >= 1.0 - 1e-15:
        # Both raters put everything in one bucket. Kappa is undefined;
        # report perfect concordance when they never diverge, else zero.
        return 1.0 if po >= 1.0 - 1e-15 else 0.0
    return (po - pe) / (1.0 - pe)


@dataclass(frozen=True)
class AgreementThresholds:
    """Pass/fail lines for pairwise concordance.

    Defaults are deliberately strict on *practical* agreement: within-ε
    rate and Cohen's κ. Exact equality is reported but not required by
    default — continuous scores almost never match bit-for-bit even when
    two judges are effectively interchangeable.
    """

    min_exact_rate: float = 0.0
    min_within_eps_rate: float = 0.9
    min_kappa: float = 0.4

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value < 0.0 or value > 1.0:
                raise ValueError(
                    f"AgreementThresholds.{name} must be in [0, 1], got {value}."
                )


DEFAULT_AGREEMENT_THRESHOLDS = AgreementThresholds()


@dataclass(frozen=True)
class PairAgreement:
    """Concordance between one ordered pair of judges."""

    judge_a: str
    judge_b: str
    cases: int
    exact_rate: float          # fraction of items with identical scores
    within_eps_rate: float     # fraction with |score_a - score_b| <= epsilon
    kappa: float               # Cohen's kappa on discretized scores
    mean_abs_delta: float      # mean |score_a - score_b|
    thresholds: AgreementThresholds = DEFAULT_AGREEMENT_THRESHOLDS

    @property
    def flagged(self) -> bool:
        return (
            self.exact_rate < self.thresholds.min_exact_rate
            or self.within_eps_rate < self.thresholds.min_within_eps_rate
            or self.kappa < self.thresholds.min_kappa
        )


@dataclass(frozen=True)
class AgreementMatrixReport:
    """Full pairwise concordance matrix for a set of judges.

    Diagonal cells are perfect self-agreement (1.0 / kappa 1.0) and are
    not stored in `pairs` — only the upper triangle of distinct pairs.
    """

    judges: tuple[str, ...]
    cases: int
    epsilon: float
    pairs: tuple[PairAgreement, ...] = ()
    scores: dict[str, tuple[float, ...]] = field(default_factory=dict)
    thresholds: AgreementThresholds = DEFAULT_AGREEMENT_THRESHOLDS

    def rate_matrix(self, *, metric: str = "within_eps") -> list[list[float]]:
        """NxN matrix of pairwise rates (or kappa). Diagonal is 1.0.

        `metric` is one of ``"exact"``, ``"within_eps"``, ``"kappa"``.
        """
        attr = {
            "exact": "exact_rate",
            "within_eps": "within_eps_rate",
            "kappa": "kappa",
        }.get(metric)
        if attr is None:
            raise ValueError(
                f"Unknown metric {metric!r}; use 'exact', 'within_eps', or 'kappa'."
            )
        n = len(self.judges)
        grid = [[1.0] * n for _ in range(n)]
        index = {name: i for i, name in enumerate(self.judges)}
        for pair in self.pairs:
            i, j = index[pair.judge_a], index[pair.judge_b]
            value = getattr(pair, attr)
            grid[i][j] = value
            grid[j][i] = value
        return grid

    def matrix(
        self,
        *,
        metric: str = "within_eps",
        fmt: str = "markdown",
    ) -> str:
        """Printable ASCII or Markdown concordance table."""
        if fmt not in {"markdown", "ascii"}:
            raise ValueError("fmt must be 'markdown' or 'ascii'.")
        grid = self.rate_matrix(metric=metric)
        names = list(self.judges)
        # Keep labels short enough that a terminal table still fits.
        labels = [name if len(name) <= 12 else name[:11] + "…" for name in names]
        col_w = max(8, max((len(label) for label in labels), default=8))

        def cell(text: str) -> str:
            return f"{text:>{col_w}}"

        header = cell("") + " " + " ".join(cell(label) for label in labels)
        rows = [header]
        for i, label in enumerate(labels):
            cells = " ".join(cell(f"{grid[i][j]:.2f}") for j in range(len(names)))
            rows.append(f"{cell(label)} {cells}")

        if fmt == "ascii":
            return "\n".join(rows)

        # Markdown: header + separator + body.
        md_header = "| " + " | ".join([""] + labels) + " |"
        sep = "| " + " | ".join(["---"] * (len(labels) + 1)) + " |"
        md_rows = [
            "| "
            + " | ".join(
                [labels[i]] + [f"{grid[i][j]:.2f}" for j in range(len(names))]
            )
            + " |"
            for i in range(len(names))
        ]
        title = f"agreement matrix ({metric}, ε={self.epsilon:g})"
        return "\n".join([title, md_header, sep, *md_rows])

    @property
    def failures(self) -> tuple[str, ...]:
        """``"a|b"`` keys for pairs that fell below thresholds."""
        return tuple(f"{p.judge_a}|{p.judge_b}" for p in self.pairs if p.flagged)

    @property
    def flagged(self) -> bool:
        return bool(self.failures)

    def to_dict(self) -> dict:
        """JSON-serializable nested dict of the full report."""
        return {
            "judges": list(self.judges),
            "cases": self.cases,
            "epsilon": self.epsilon,
            "flagged": self.flagged,
            "failures": list(self.failures),
            "thresholds": {
                "min_exact_rate": self.thresholds.min_exact_rate,
                "min_within_eps_rate": self.thresholds.min_within_eps_rate,
                "min_kappa": self.thresholds.min_kappa,
            },
            "scores": {name: list(vals) for name, vals in self.scores.items()},
            "pairs": [
                {
                    "judge_a": p.judge_a,
                    "judge_b": p.judge_b,
                    "cases": p.cases,
                    "exact_rate": p.exact_rate,
                    "within_eps_rate": p.within_eps_rate,
                    "kappa": p.kappa,
                    "mean_abs_delta": p.mean_abs_delta,
                    "flagged": p.flagged,
                }
                for p in self.pairs
            ],
            "matrices": {
                "exact": self.rate_matrix(metric="exact"),
                "within_eps": self.rate_matrix(metric="within_eps"),
                "kappa": self.rate_matrix(metric="kappa"),
            },
        }

    def summary(self) -> str:
        """Human-readable one-line-per-pair report plus the matrix."""
        lines = [
            f"judges: {', '.join(self.judges)}",
            f"cases: {self.cases}  epsilon: {self.epsilon:g}",
        ]
        for pair in self.pairs:
            lines.append(
                f"  {pair.judge_a} vs {pair.judge_b}  "
                f"exact={pair.exact_rate:.0%}  "
                f"within_ε={pair.within_eps_rate:.0%}  "
                f"κ={pair.kappa:.2f}  "
                f"|Δ|={pair.mean_abs_delta:.3f}  "
                f"flagged={pair.flagged}"
            )
        lines.append(self.matrix(metric="within_eps", fmt="ascii"))
        verdict = (
            f"FLAGGED pairs: {', '.join(self.failures)}"
            if self.flagged
            else "PASSED all pairs"
        )
        lines.append(verdict)
        return "\n".join(lines)


def _discretize(score: float, decimals: int) -> float:
    """Bucket a continuous score for categorical kappa."""
    return round(score, decimals)


def agreement_matrix(
    judges: list[Judge],
    cases: list[tuple[str, str]],
    rubric: str,
    *,
    epsilon: float = 0.05,
    kappa_decimals: int = 1,
    thresholds: AgreementThresholds = DEFAULT_AGREEMENT_THRESHOLDS,
    max_workers: int = 1,
) -> AgreementMatrixReport:
    """Score every case with every judge and build the concordance matrix.

    Each case is a ``(prompt, response)`` pair. Pass distinct judges, or
    wrap one judge under several names/prompt variants — the audit only
    needs objects that implement ``judge()`` with unique ``name`` values.
    """
    if len(judges) < 2:
        raise ValueError("agreement_matrix needs at least two judges.")
    if not cases:
        raise ValueError("agreement_matrix needs at least one case.")
    if epsilon < 0.0:
        raise ValueError("epsilon must be non-negative.")
    if kappa_decimals < 0:
        raise ValueError("kappa_decimals must be non-negative.")

    names = [j.name for j in judges]
    if len(set(names)) != len(names):
        raise ValueError("Judge names must be unique within an agreement matrix.")

    def score_one(item: tuple[Judge, str, str]) -> float:
        judge, prompt, response = item
        return judge.judge(prompt=prompt, response=response, rubric=rubric).score

    # Flatten (judge, case) work so max_workers can parallelise the whole grid
    # without changing result order.
    work: list[tuple[Judge, str, str]] = [
        (judge, prompt, response)
        for judge in judges
        for prompt, response in cases
    ]
    flat = _map(score_one, work, max_workers)

    per_judge: dict[str, list[float]] = {name: [] for name in names}
    cursor = 0
    for judge in judges:
        n = len(cases)
        per_judge[judge.name] = list(flat[cursor : cursor + n])
        cursor += n

    pairs: list[PairAgreement] = []
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            a_scores = per_judge[left]
            b_scores = per_judge[right]
            n = len(a_scores)
            exact = sum(sa == sb for sa, sb in zip(a_scores, b_scores)) / n
            within = (
                sum(abs(sa - sb) <= epsilon for sa, sb in zip(a_scores, b_scores)) / n
            )
            deltas = [abs(sa - sb) for sa, sb in zip(a_scores, b_scores)]
            labels_a = [_discretize(s, kappa_decimals) for s in a_scores]
            labels_b = [_discretize(s, kappa_decimals) for s in b_scores]
            pairs.append(
                PairAgreement(
                    judge_a=left,
                    judge_b=right,
                    cases=n,
                    exact_rate=exact,
                    within_eps_rate=within,
                    kappa=cohen_kappa(labels_a, labels_b),
                    mean_abs_delta=sum(deltas) / n,
                    thresholds=thresholds,
                )
            )

    return AgreementMatrixReport(
        judges=tuple(names),
        cases=len(cases),
        epsilon=epsilon,
        pairs=tuple(pairs),
        scores={name: tuple(vals) for name, vals in per_judge.items()},
        thresholds=thresholds,
    )
