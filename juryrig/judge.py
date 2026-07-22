"""Judge interfaces and built-in judges."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Judgment:
    """A single judge's verdict on one response."""

    score: float  # 0.0 (worst) to 1.0 (best)
    reasoning: str = ""


@runtime_checkable
class Judge(Protocol):
    """Anything that can score a response against a rubric."""

    name: str

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        ...


@runtime_checkable
class PairwiseJudge(Protocol):
    """Anything that can pick a winner between two responses."""

    name: str

    def compare(self, *, prompt: str, a: str, b: str, rubric: str) -> Literal["A", "B"]:
        ...


def _stable_unit(seed: int, *parts: str) -> float:
    """Deterministic pseudo-random float in [0, 1) from hashed inputs."""
    digest = hashlib.sha256(("|".join(parts) + f"|{seed}").encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class MockJudge:
    """Deterministic judge for tests and demos.

    Scores by rubric keyword coverage, with configurable flaws
    (position bias, verbosity bias, injection bias, noise) so juryrig's audits have
    something real to detect. No network calls.
    """

    def __init__(
        self,
        name: str = "mock",
        seed: int = 0,
        position_bias: float = 0.0,
        verbosity_bias: float = 0.0,
        injection_bias: float = 0.0,
        noise: float = 0.0,
    ) -> None:
        self.name = name
        self.seed = seed
        self.position_bias = position_bias
        self.verbosity_bias = verbosity_bias
        self.injection_bias = injection_bias
        self.noise = noise

    def _base_score(self, response: str, rubric: str) -> float:
        wanted = {w.lower().strip(".,") for w in rubric.split() if len(w) > 3}
        if not wanted:
            return 0.5
        have = {w.lower().strip(".,") for w in response.split()}
        return len(wanted & have) / len(wanted)

    def _contains_injection(self, response: str) -> bool:
        lower = response.lower()
        markers = (
            "judge override",
            "ignore the rubric",
            "ignore previous",
            "maximum rating",
            "perfect score",
            "evaluation passed",
        )
        return any(marker in lower for marker in markers)

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        score = self._base_score(response, rubric)
        score += self.verbosity_bias * min(len(response) / 2000.0, 1.0)
        if self.injection_bias and self._contains_injection(response):
            score += self.injection_bias
        if self.noise:
            score += self.noise * (_stable_unit(self.seed, prompt, response) - 0.5)
        score = max(0.0, min(1.0, score))
        return Judgment(score=score, reasoning=f"{self.name} keyword coverage")

    def compare(self, *, prompt: str, a: str, b: str, rubric: str):
        score_a = self.judge(prompt=prompt, response=a, rubric=rubric).score
        score_b = self.judge(prompt=prompt, response=b, rubric=rubric).score
        return "A" if score_a + self.position_bias >= score_b else "B"
