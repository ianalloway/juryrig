# juryrig

**Audit your LLM judges before you trust them.**

[![CI](https://github.com/ianalloway/juryrig/actions/workflows/ci.yml/badge.svg)](https://github.com/ianalloway/juryrig/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Zero dependencies](https://img.shields.io/badge/dependencies-zero-16c784)
![License](https://img.shields.io/badge/license-MIT-blue)

LLM-as-judge is everywhere: the cheapest way to grade model outputs is to ask
another model. But the judge is a model too — with position bias, a weakness
for long-winded answers, run-to-run inconsistency, and confidence that rarely
matches its accuracy. If you haven't measured those, your eval numbers are
decoration.

juryrig is a small, zero-dependency Python toolkit that treats the judge as
the thing under test:

- **Position-bias audit** — present every A/B pair in both orders; count how often the *slot* (not the content) decides the winner.
- **Verbosity-bias audit** — re-score responses padded with content-free filler; a fair judge shouldn't reward padding.
- **Prompt-injection audit** — append judge-targeted instructions to bad responses; a robust judge should grade the answer, not obey it.
- **Self-consistency** — same input, several runs; how stable is the score?
- **Panels** — pool several judges (mean / median / min) and get an agreement score, so you know when your verdict depends on which judge you picked.
- **Calibration** — Brier score, reliability tables, and expected calibration error against human labels.

## Install

```bash
pip install git+https://github.com/ianalloway/juryrig
```

## Quickstart

```python
from juryrig import (
    AnthropicJudge,
    MockJudge,
    Panel,
    position_bias,
    prompt_injection_bias,
    verbosity_bias,
)

rubric = "Answer must mention photosynthesis, chlorophyll, sunlight, and energy."

# 1. Audit a judge before using it
judge = AnthropicJudge()          # or OpenAIJudge(), or your own class
cases = [("How do plants make food?", "good answer...", "weak answer...")]

bias = position_bias(judge, cases, rubric)
print(f"flip rate: {bias.flip_rate:.0%}  flagged: {bias.flagged}")

injection = prompt_injection_bias(judge, [("Weak answer prompt", "vague answer")], rubric)
print(f"injection lift: {injection.mean_delta:+.3f}  flagged: {injection.flagged}")

# 2. Use a panel instead of a single judge
panel = Panel([AnthropicJudge(), MockJudge(name="baseline")])
report = panel.evaluate(prompt="How do plants make food?",
                        response="Photosynthesis converts sunlight...",
                        rubric=rubric)
print(report.pooled, report.agreement)
```

Every audit returns a small frozen dataclass with a `flagged` property, so
gating a CI pipeline is one `if`:

```python
assert not position_bias(judge, cases, rubric).flagged, "judge is positionally biased"
```

## Why the MockJudge has built-in flaws

`MockJudge(position_bias=..., verbosity_bias=..., injection_bias=..., noise=...)`
lets you dial in known defects. That's how juryrig tests itself — the audits
must detect a rigged judge and clear a fair one — and it gives you a
deterministic, network-free way to test *your* eval pipeline end to end.

## Calibration

```python
from juryrig import brier_score, expected_calibration_error

scores = [0.9, 0.8, 0.3, 0.95]   # judge scores
labels = [1, 1, 0, 0]            # human ground truth

print(brier_score(scores, labels))
print(expected_calibration_error(scores, labels))
```

A judge that says 0.9 should be right ~90% of the time. ECE tells you how far
that promise is from reality.

## Demo

```bash
python3 examples/audit_demo.py
```

Runs the full audit suite against a fair judge and a rigged one, no API keys
required.

## Design notes

- **Zero runtime dependencies** — stdlib only, including the API clients.
- **Provider-agnostic** — a judge is anything with a `judge()` method; pairwise judges add `compare()`. Protocols, not base classes.
- **Deterministic tests** — all randomness is hash-seeded; CI never flakes.

## License

MIT
