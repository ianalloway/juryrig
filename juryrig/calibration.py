"""Calibration of judge scores against human labels.

A judge that says 0.9 should be right about 90% of the time. These
helpers quantify how far a judge's confidence is from reality.
"""
from __future__ import annotations

from dataclasses import dataclass


def brier_score(scores: list[float], labels: list[int]) -> float:
    """Mean squared error between scores and binary human labels (lower is better)."""
    _check(scores, labels)
    return sum((s - y) ** 2 for s, y in zip(scores, labels)) / len(scores)


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_score: float
    accuracy: float


def reliability_table(
    scores: list[float], labels: list[int], bins: int = 10
) -> list[CalibrationBin]:
    """Bucket scores and compare each bucket's mean score to its accuracy."""
    _check(scores, labels)
    table = []
    for i in range(bins):
        lower, upper = i / bins, (i + 1) / bins
        members = [
            (s, y)
            for s, y in zip(scores, labels)
            if lower <= s < upper or (i == bins - 1 and s == 1.0)
        ]
        if not members:
            continue
        bucket_scores = [s for s, _ in members]
        bucket_labels = [y for _, y in members]
        table.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=len(members),
                mean_score=sum(bucket_scores) / len(members),
                accuracy=sum(bucket_labels) / len(members),
            )
        )
    return table


def expected_calibration_error(
    scores: list[float], labels: list[int], bins: int = 10
) -> float:
    """Weighted mean |confidence - accuracy| across bins. 0 = perfectly calibrated."""
    _check(scores, labels)
    total = len(scores)
    return sum(
        b.count / total * abs(b.mean_score - b.accuracy)
        for b in reliability_table(scores, labels, bins)
    )


def _check(scores: list[float], labels: list[int]) -> None:
    if len(scores) != len(labels):
        raise ValueError("scores and labels must be the same length.")
    if not scores:
        raise ValueError("Need at least one (score, label) pair.")
    if any(not 0.0 <= s <= 1.0 for s in scores):
        raise ValueError("Scores must be in [0, 1].")
    if any(y not in (0, 1) for y in labels):
        raise ValueError("Labels must be 0 or 1.")
