"""Disagreement atlas — where multi-judge panels split.

Given scores already collected by :func:`juryrig.agreement.agreement_matrix`
(or the same inputs that produce them), rank items by how much judges
diverge, group items by which judge pairs disagree, and measure each
judge's contrarian rate against the panel consensus.

Builds on :class:`~juryrig.agreement.AgreementMatrixReport` rather than
re-scoring or re-implementing pairwise concordance.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal, Sequence

from .agreement import AgreementMatrixReport, _discretize, agreement_matrix
from .judge import Judge

RankingMetric = Literal["variance", "pairwise", "entropy"]


def _population_variance(values: Sequence[float]) -> float:
    """Population variance of a score vector (0.0 when fewer than two values)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / n


def _shannon_entropy(labels: Sequence[object]) -> float:
    """Shannon entropy (bits) of a categorical label multiset."""
    n = len(labels)
    if n == 0:
        return 0.0
    counts = Counter(labels)
    entropy = 0.0
    for count in counts.values():
        if count == 0:
            continue
        p = count / n
        entropy -= p * math.log2(p)
    return entropy


def _median(values: Sequence[float]) -> float:
    """Median of a non-empty sequence (average of middle two when even)."""
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _pair_key(left: str, right: str) -> str:
    """Stable ``a|b`` key matching :class:`~juryrig.agreement.AgreementMatrixReport`."""
    return f"{left}|{right}"


@dataclass(frozen=True)
class ItemDisagreement:
    """Per-item disagreement summary across the panel."""

    index: int
    scores: dict[str, float]
    variance: float
    pairwise_disagreement: float  # fraction of judge pairs beyond epsilon
    entropy: float  # Shannon entropy of discretized scores (bits)
    split_pairs: tuple[str, ...]  # ``"a|b"`` keys that disagree on this item
    ranking_score: float  # the metric used to order the atlas


@dataclass(frozen=True)
class SplitCluster:
    """Items that share the same set of disagreeing judge pairs."""

    split_pairs: tuple[str, ...]
    item_indices: tuple[int, ...]

    @property
    def size(self) -> int:
        return len(self.item_indices)


@dataclass(frozen=True)
class ContrarianRate:
    """How often one judge diverges from the panel consensus (median)."""

    judge: str
    rate: float
    items: tuple[int, ...]  # item indices where this judge was contrarian
    cases: int

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class DisagreementAtlas:
    """Structured map of where a multi-judge panel disagrees.

    **Ordering (deterministic tie-breakers):**

    - *Items* are sorted by ``ranking_score`` descending, then by ``index``
      ascending when scores tie (including bit-equal floating-point ties).
    - *Clusters* are sorted by ``size`` descending, then by ``split_pairs``
      lexicographically ascending. Indices inside a cluster are ascending.
    - *Contrarian* entries follow the judge order from the source report.

    Ranking metrics choose ``ranking_score`` (variance / pairwise rate /
    entropy); they do not change the tie-break rules above.
    """

    judges: tuple[str, ...]
    cases: int
    epsilon: float
    ranking: RankingMetric
    items: tuple[ItemDisagreement, ...]
    clusters: tuple[SplitCluster, ...]
    contrarian: tuple[ContrarianRate, ...]

    def to_dict(self) -> dict:
        """JSON-serializable nested dict of the full atlas."""
        return {
            "judges": list(self.judges),
            "cases": self.cases,
            "epsilon": self.epsilon,
            "ranking": self.ranking,
            "items": [
                {
                    "index": item.index,
                    "scores": dict(item.scores),
                    "variance": item.variance,
                    "pairwise_disagreement": item.pairwise_disagreement,
                    "entropy": item.entropy,
                    "split_pairs": list(item.split_pairs),
                    "ranking_score": item.ranking_score,
                }
                for item in self.items
            ],
            "clusters": [
                {
                    "split_pairs": list(cluster.split_pairs),
                    "item_indices": list(cluster.item_indices),
                    "size": cluster.size,
                }
                for cluster in self.clusters
            ],
            "contrarian": [
                {
                    "judge": entry.judge,
                    "rate": entry.rate,
                    "count": entry.count,
                    "cases": entry.cases,
                    "items": list(entry.items),
                }
                for entry in self.contrarian
            ],
        }

    def table(self, *, fmt: str = "ascii", top: int | None = None) -> str:
        """Printable ranking table (ASCII or Markdown)."""
        if fmt not in {"markdown", "ascii"}:
            raise ValueError("fmt must be 'markdown' or 'ascii'.")
        rows = self.items if top is None else self.items[: max(0, top)]
        headers = ("#", "var", "pair", "H", "splits")

        def fmt_row(cells: Sequence[str]) -> str:
            if fmt == "ascii":
                widths = (4, 8, 8, 8, 24)
                return " ".join(f"{c:<{w}}" for c, w in zip(cells, widths))
            return "| " + " | ".join(cells) + " |"

        lines: list[str] = []
        if fmt == "markdown":
            lines.append(f"disagreement atlas (ranking={self.ranking})")
        lines.append(fmt_row(headers))
        if fmt == "markdown":
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        elif fmt == "ascii":
            lines.append(fmt_row(("-" * 4, "-" * 8, "-" * 8, "-" * 8, "-" * 24)))

        for item in rows:
            splits = ",".join(item.split_pairs) if item.split_pairs else "—"
            if len(splits) > 22 and fmt == "ascii":
                splits = splits[:21] + "…"
            lines.append(
                fmt_row(
                    (
                        str(item.index),
                        f"{item.variance:.4f}",
                        f"{item.pairwise_disagreement:.2f}",
                        f"{item.entropy:.3f}",
                        splits,
                    )
                )
            )
        return "\n".join(lines)

    def summary(self, *, top: int = 10, fmt: str = "ascii") -> str:
        """Human-readable atlas: ranking table, clusters, contrarian rates."""
        lines = [
            f"judges: {', '.join(self.judges)}",
            f"cases: {self.cases}  epsilon: {self.epsilon:g}  ranking: {self.ranking}",
            "",
            "ranked items (highest disagreement first):",
            self.table(fmt=fmt, top=top),
            "",
            "split clusters:",
        ]
        if not self.clusters:
            lines.append("  (none — judges agreed on every item)")
        else:
            for cluster in self.clusters:
                pairs = (
                    ", ".join(cluster.split_pairs)
                    if cluster.split_pairs
                    else "(no splits)"
                )
                indices = ", ".join(str(i) for i in cluster.item_indices)
                lines.append(
                    f"  [{cluster.size}] pairs={{{pairs}}}  items=[{indices}]"
                )
        lines.append("")
        lines.append("contrarian rates (vs median):")
        for entry in self.contrarian:
            lines.append(
                f"  {entry.judge}: {entry.rate:.0%} "
                f"({entry.count}/{entry.cases})"
            )
        return "\n".join(lines)

    def to_markdown(self, *, top: int = 10) -> str:
        """Full atlas rendered as Markdown (ranking + clusters + rates)."""
        lines = [
            "# Disagreement atlas",
            "",
            f"- Judges: {', '.join(f'`{j}`' for j in self.judges)}",
            f"- Cases: {self.cases}",
            f"- Epsilon: `{self.epsilon:g}`",
            f"- Ranking: `{self.ranking}`",
            "",
            "## Ranked items",
            "",
            self.table(fmt="markdown", top=top),
            "",
            "## Split clusters",
            "",
        ]
        if not self.clusters:
            lines.append("Judges agreed on every item.")
        else:
            lines.append("| size | split pairs | items |")
            lines.append("| --- | --- | --- |")
            for cluster in self.clusters:
                pairs = (
                    ", ".join(f"`{p}`" for p in cluster.split_pairs)
                    if cluster.split_pairs
                    else "_(none)_"
                )
                indices = ", ".join(str(i) for i in cluster.item_indices)
                lines.append(f"| {cluster.size} | {pairs} | {indices} |")
        lines.extend(["", "## Contrarian rates", ""])
        lines.append("| judge | rate | count |")
        lines.append("| --- | --- | --- |")
        for entry in self.contrarian:
            lines.append(
                f"| `{entry.judge}` | {entry.rate:.0%} | "
                f"{entry.count}/{entry.cases} |"
            )
        return "\n".join(lines)


def _ranking_value(item: ItemDisagreement, ranking: RankingMetric) -> float:
    if ranking == "variance":
        return item.variance
    if ranking == "pairwise":
        return item.pairwise_disagreement
    if ranking == "entropy":
        return item.entropy
    # Exhaustive for RankingMetric; keep mypy/ruff honest if the alias grows.
    raise ValueError(
        f"Unknown ranking {ranking!r}; use 'variance', 'pairwise', or 'entropy'."
    )


def disagreement_atlas_from_report(
    report: AgreementMatrixReport,
    *,
    ranking: RankingMetric = "variance",
    kappa_decimals: int = 1,
) -> DisagreementAtlas:
    """Build an atlas from an existing :class:`AgreementMatrixReport`.

    Reuses ``report.scores`` and ``report.epsilon`` — no extra judge calls.

    Item order: ``ranking_score`` descending, then item ``index`` ascending.
    Cluster order: cluster size descending, then ``split_pairs``
    lexicographically ascending (indices within a cluster ascending).
    """
    if ranking not in {"variance", "pairwise", "entropy"}:
        raise ValueError(
            f"Unknown ranking {ranking!r}; use 'variance', 'pairwise', or 'entropy'."
        )
    if kappa_decimals < 0:
        raise ValueError("kappa_decimals must be non-negative.")
    if report.cases < 1:
        raise ValueError("disagreement atlas needs at least one case.")
    if len(report.judges) < 2:
        raise ValueError("disagreement atlas needs at least two judges.")

    names = list(report.judges)
    n_cases = report.cases
    for name in names:
        if name not in report.scores:
            raise ValueError(f"AgreementMatrixReport is missing scores for {name!r}.")
        if len(report.scores[name]) != n_cases:
            raise ValueError(
                f"Score length for {name!r} ({len(report.scores[name])}) "
                f"does not match cases ({n_cases})."
            )

    items: list[ItemDisagreement] = []
    for idx in range(n_cases):
        scores = {name: report.scores[name][idx] for name in names}
        values = [scores[name] for name in names]
        variance = _population_variance(values)

        split_pairs: list[str] = []
        pair_total = 0
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                pair_total += 1
                if abs(scores[left] - scores[right]) > report.epsilon:
                    split_pairs.append(_pair_key(left, right))
        pairwise = (len(split_pairs) / pair_total) if pair_total else 0.0

        labels = [_discretize(scores[name], kappa_decimals) for name in names]
        entropy = _shannon_entropy(labels)

        draft = ItemDisagreement(
            index=idx,
            scores=scores,
            variance=variance,
            pairwise_disagreement=pairwise,
            entropy=entropy,
            split_pairs=tuple(split_pairs),
            ranking_score=0.0,
        )
        items.append(
            ItemDisagreement(
                index=draft.index,
                scores=draft.scores,
                variance=draft.variance,
                pairwise_disagreement=draft.pairwise_disagreement,
                entropy=draft.entropy,
                split_pairs=draft.split_pairs,
                ranking_score=_ranking_value(draft, ranking),
            )
        )

    items.sort(key=lambda item: (-item.ranking_score, item.index))

    # Cluster by identical split-pair signature. Order is independent of
    # ranking appearance: larger clusters first, then lexicographic signature.
    buckets: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for item in items:
        buckets[item.split_pairs].append(item.index)
    clusters = tuple(
        SplitCluster(
            split_pairs=key,
            item_indices=tuple(sorted(indices)),
        )
        for key, indices in sorted(
            buckets.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )
    )

    # Contrarian vs median: |score - median| > epsilon.
    contrarian_hits: dict[str, list[int]] = {name: [] for name in names}
    for idx in range(n_cases):
        values = [report.scores[name][idx] for name in names]
        consensus = _median(values)
        for name in names:
            if abs(report.scores[name][idx] - consensus) > report.epsilon:
                contrarian_hits[name].append(idx)

    contrarian = tuple(
        ContrarianRate(
            judge=name,
            rate=(len(contrarian_hits[name]) / n_cases) if n_cases else 0.0,
            items=tuple(contrarian_hits[name]),
            cases=n_cases,
        )
        for name in names
    )

    return DisagreementAtlas(
        judges=tuple(names),
        cases=n_cases,
        epsilon=report.epsilon,
        ranking=ranking,
        items=tuple(items),
        clusters=clusters,
        contrarian=contrarian,
    )


def disagreement_atlas(
    judges: list[Judge] | AgreementMatrixReport,
    cases: list[tuple[str, str]] | None = None,
    rubric: str | None = None,
    *,
    epsilon: float = 0.05,
    kappa_decimals: int = 1,
    ranking: RankingMetric = "variance",
    max_workers: int = 1,
) -> DisagreementAtlas:
    """Map where judges disagree across a set of items.

    Pass an existing :class:`AgreementMatrixReport` to analyse scores already
    collected, or pass ``judges``, ``cases``, and ``rubric`` to score first
    via :func:`~juryrig.agreement.agreement_matrix` and then build the atlas.
    """
    if isinstance(judges, AgreementMatrixReport):
        if cases is not None or rubric is not None:
            raise ValueError(
                "When passing an AgreementMatrixReport, omit cases and rubric."
            )
        return disagreement_atlas_from_report(
            judges, ranking=ranking, kappa_decimals=kappa_decimals
        )

    if cases is None or rubric is None:
        raise ValueError(
            "disagreement_atlas(judges, cases, rubric) requires cases and rubric, "
            "or pass an AgreementMatrixReport as the first argument."
        )
    report = agreement_matrix(
        judges,
        cases,
        rubric,
        epsilon=epsilon,
        kappa_decimals=kappa_decimals,
        max_workers=max_workers,
    )
    return disagreement_atlas_from_report(
        report, ranking=ranking, kappa_decimals=kappa_decimals
    )
