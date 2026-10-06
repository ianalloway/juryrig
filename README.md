# juryrig

**Audit your LLM judges before you trust them.**

[![CI](https://github.com/ianalloway/juryrig/actions/workflows/ci.yml/badge.svg)](https://github.com/ianalloway/juryrig/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/juryrig)](https://pypi.org/project/juryrig/)
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
- **Panels** — pool several judges (mean / median / min) and get an agreement score, so you know when your verdict depends on which judge you picked. Pairwise panels vote on A/B pairs and report a dead heat as one.
- **Agreement matrix** — score the same items with N judges (or prompt variants) and print pairwise exact / within-ε rates plus Cohen's κ — a concordance audit for the panel you are about to trust.
- **Disagreement atlas (development only)** — rank items by variance / pairwise split / categorical entropy, cluster by which judge pairs diverge, and report per-judge contrarian rates. See [development setup](#development-checkout-unreleased-atlas).
- **Calibration** — Brier score, reliability tables, and expected calibration error against human labels.

Run the whole battery with `audit_suite()`, or from the command line with
`juryrig cases.json`.

## Install

### Stable release (0.3.0)

```bash
python -m pip install "juryrig==0.3.0"
```

The quickstart, audits, panels, calibration, and `juryrig agree` examples
below work with **0.3.0**. The `disagreement_atlas` API and `juryrig atlas`
command are **unreleased** and require the development checkout described
below; they are not available in the published 0.3.0 package.

| Capability | PyPI 0.3.0 | Development (`main`) |
|---|---|---|
| Audits, panels, calibration, provider adapters | Available | Available |
| `agreement_matrix()` / `juryrig agree` | Available | Available |
| `disagreement_atlas()` / `juryrig atlas` | Not available | Unreleased |

### Development checkout (unreleased atlas)

Use a separate virtual environment for development. From a source checkout:

```bash
git clone https://github.com/ianalloway/juryrig.git
cd juryrig
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
juryrig atlas examples/cases.json --seeds 0,1,2
```

`main` can change before the next release. Its package version still reads
`0.3.0`, so the version string alone does not identify atlas support. See the
[Unreleased changelog](CHANGELOG.md#unreleased) for development-only features.

Requires Python 3.10+. Package page: [pypi.org/project/juryrig](https://pypi.org/project/juryrig/).
Source: [github.com/ianalloway/juryrig](https://github.com/ianalloway/juryrig).

## Quickstart

```python
from juryrig import (
    MockJudge,
    Panel,
    position_bias,
    prompt_injection_bias,
)

rubric = "photosynthesis chlorophyll sunlight energy"

# 1. Audit a judge before using it
judge = MockJudge(name="demo")    # swap in your own judge for real audits
cases = [(
    "How do plants make food?",
    "Plants use photosynthesis: chlorophyll captures sunlight energy.",
    "Plants eat soil.",
)]

bias = position_bias(judge, cases, rubric)
print(f"flip rate: {bias.flip_rate:.0%}  flagged: {bias.flagged}")

injection = prompt_injection_bias(judge, [("Weak answer prompt", "vague answer")], rubric)
print(f"injection lift: {injection.mean_delta:+.3f}  flagged: {injection.flagged}")

# 2. Use a panel instead of a single judge
panel = Panel([MockJudge(name="primary"), MockJudge(name="baseline")])
report = panel.evaluate(prompt="How do plants make food?",
                        response=cases[0][1],
                        rubric=rubric)
print(report.pooled, report.agreement)
```

`position_bias()` is a pairwise audit and needs a judge with `compare()`;
`MockJudge` implements both `compare()` and `judge()` so the quickstart runs
without API credentials.

## The whole battery in one call

Continuing with `cases` and `rubric` from the quickstart,
`audit_suite()` runs every audit and pools the verdicts. Each case is a
`(prompt, good_response, weak_response)` triple: the pair drives the position
comparison, the good response gets padded to detect verbosity bias, and the
weak one carries the injection payload.

```python
from juryrig import MockJudge, audit_suite

report = audit_suite(MockJudge(), cases, rubric)

print(report.summary())
assert not report.flagged, f"judge failed: {report.failures}"
```

`report.failures` names the audits that tripped (`("position", "injection")`).
If the judge has no `compare()`, the position audit is reported in
`report.skipped` rather than silently counted as a pass.

## Ties

`compare()` may return `"tie"` as well as `"A"` or `"B"`. It's optional — a
judge that only ever picks a side is unaffected — but real judges often want
to call two answers equivalent, and forcing that into a coin flip manufactures
position bias that isn't there.

How `position_bias()` accounts for them:

- **Tying both ways is not a flip.** The judge gave the same answer in both
  orders, which is consistency, not order-dependence.
- **Tying one way and picking the other way *is* a flip.** The verdict changed
  when only the order changed — that's the thing being measured.
- **Ties are excluded from `first_slot_wins`.** Counting them as "not won by
  the first slot" would drag the ratio to 0 and flag a judge that ties
  everything as maximally biased toward slot two. With nothing decisive to go
  on the audit reports 0.5: no evidence of skew. The count is kept in
  `report.ties` so it stays visible rather than silently dropped.

## Panels of pairwise judges

`Panel.evaluate()` pools scores; `Panel.compare()` pools A/B votes by majority:

```python
verdict = panel.compare(prompt="How do plants make food?",
                        a="Photosynthesis converts sunlight...",
                        b="Plants eat soil.",
                        rubric=rubric)

print(verdict.winner, verdict.agreement, verdict.votes)
```

An even split sets `winner` to `None` and `deadlocked` to `True`, rather than
picking a side. A coin-flip winner would hide exactly the disagreement you
convened a panel to find. Judges without `compare()` are rejected by name —
silently dropping them would move the verdict while leaving `agreement`
looking healthy.

## Going faster against a real judge

`audit_suite` on N cases is roughly 4N judge calls, which is minutes of wall
time over a network. `max_workers` runs them in parallel:

```python
report = audit_suite(judge, cases, rubric, max_workers=8)
```

Serial by default, because a judge may be stateful or rate-limited and
threading one behind your back would be a surprise. Results are collected in
input order, so a report is identical no matter how many workers produced it
— workers are a speed knob, never a correctness one. Your judge must be
thread-safe to raise it. The CLI exposes the same thing as `--workers`.

## Tuning what counts as a failure

Every `flagged` verdict comes from a `Thresholds` object. The defaults are
strict on purpose, but they're yours to move:

```python
from juryrig import Thresholds, audit_suite

report = audit_suite(judge, cases, rubric, thresholds=Thresholds(
    injection_max_delta=0.05,   # stricter: near-zero tolerance for injection
    verbosity_mean_delta=0.10,  # looser: this judge is allowed to like detail
))
```

The measurements never change — only the line between pass and fail. Each
report carries the `thresholds` it was judged against, so a stored report
still explains its own verdict. A case file can set them too, under a
`"thresholds"` key; unknown keys are rejected rather than ignored, so a typo
can't silently leave the strict default in force.

## Command line (stable 0.3.0)

Save this as `cases.json` in your working directory. For a larger case file,
see [`examples/cases.json`](examples/cases.json) in the source checkout:

```json
{
  "rubric": "photosynthesis chlorophyll sunlight energy",
  "cases": [
    {
      "prompt": "How do plants make food?",
      "good": "Plants use photosynthesis: chlorophyll captures sunlight energy.",
      "weak": "Plants eat soil."
    }
  ]
}
```

```bash
juryrig cases.json                               # audit the built-in MockJudge
juryrig agree cases.json --seeds 0,1,2            # pairwise concordance matrix
juryrig agree cases.json --seeds 0,1,2 --json      # export the score grid
```

To audit a live provider instead, set its API key and run
`juryrig cases.json --provider anthropic --json` (makes billable API calls).

The case file is `{"rubric": ..., "cases": [{"prompt", "good", "weak"}, ...]}`.
The command exits `1` when the judge is flagged and `2` on bad input, so a CI
step is one line. The equivalent module entry point is `python -m juryrig cases.json`
(after installation, or from the repository root).
`juryrig agree` scores each case's `good` response with every judge slot and
prints an ASCII (or `--fmt markdown`) concordance matrix; `--json` emits the
full nested structure including exact / within-ε / κ matrices.

### Optional: provider-backed judges

`AnthropicJudge` and `OpenAIJudge` wrap the Anthropic/OpenAI HTTP APIs
(stdlib-only, no extra dependencies) and work with the single-response
audits. They're not exported from the top-level package — import them
explicitly when you need a live model:

```python
from juryrig.providers import AnthropicJudge, OpenAIJudge  # needs *_API_KEY env var
```

An audit is many calls in a row, so both retry transient failures (429, 5xx,
network errors) with exponential backoff — one flaky response shouldn't throw
away every result collected before it. A numeric `Retry-After` is honoured.
Client errors like 401 and 404 fail fast, since they'd fail identically on
every attempt.

```python
from juryrig.providers import AnthropicJudge, RetryPolicy

judge = AnthropicJudge(retry=RetryPolicy(attempts=5, backoff=1.0))
```

### Optional: any OpenAI-compatible endpoint (`HttpJudge`)

`OpenAIJudge` / `AnthropicJudge` target those vendors' hosted APIs.
`HttpJudge` talks to **any** server that speaks the OpenAI chat-completions
wire format — Ollama, vLLM, LM Studio, OpenRouter, a company gateway, a
local fine-tune — still with zero extra dependencies:

```python
from juryrig.http_judge import HttpJudge
from juryrig import audit_suite

judge = HttpJudge(
    url="http://127.0.0.1:11434/v1/chat/completions",  # full endpoint URL
    model="llama3.2",
    # api_key="…"                 # optional; or set OPENAI_API_KEY
    # headers={"X-Tenant": "dev"} # optional extra headers
)

# Implements both judge() and compare(), so the full suite — including
# position bias — runs against the live model.
report = audit_suite(judge, cases, rubric, max_workers=4)
print(report.summary())
```

Point `url` at the full chat-completions path your server exposes. An API
key is optional (many local servers need none). When one is required, pass
`api_key=` or set the env named by `api_key_env` (default `OPENAI_API_KEY`).
Retries use the same `RetryPolicy` as the provider judges.

Every audit returns a small frozen dataclass with a `flagged` property, so
gating a CI pipeline is one `if`:

```python
assert not position_bias(judge, cases, rubric).flagged, "judge is positionally biased"
```

## Why the MockJudge has built-in flaws

`MockJudge(position_bias=..., verbosity_bias=..., injection_bias=...,
noise=..., instability=..., tie_margin=...)` lets you dial in known defects.
That's how juryrig tests itself — the audits must detect a rigged judge and
clear a fair one — and it gives you a deterministic, network-free way to test
*your* eval pipeline end to end.

`noise` and `instability` are not the same knob, and the difference trips
people up:

- **`noise`** is seeded on the input, so re-judging one response returns the
  same score forever. It perturbs scores *across* responses.
- **`instability`** is seeded on a call counter, so the same input scores
  differently each time. It's the only flaw `self_consistency()` can detect —
  a judge with `noise=0.9` reports a spread of exactly `0.0`.

Instability is still reproducible: a fresh `MockJudge` replays the same
sequence, so switching the flaw on doesn't make your tests flaky.

`tie_margin` makes the judge answer `"tie"` when two responses score within
it. Useful for exercising tie handling — and note that *without* it, two
identical answers are handed to slot A by `compare()`'s tie-break, which the
position audit correctly reports as bias.

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

## Pairwise agreement matrix

Before you pool judges into a panel, check whether they actually agree on the
same items. `agreement_matrix()` scores every `(prompt, response)` with every
judge and reports pairwise exact match, within-ε rates, and Cohen's κ
(stdlib-only — no scipy):

```python
from juryrig import MockJudge, agreement_matrix

rubric = "photosynthesis chlorophyll sunlight energy"
report = agreement_matrix(
    [MockJudge(name="primary", seed=0), MockJudge(name="shadow", seed=1)],
    [("How do plants make food?", "Photosynthesis converts sunlight...")],
    rubric,
    epsilon=0.05,
)
print(report.summary())          # per-pair rates + ASCII matrix
print(report.matrix(fmt="markdown"))
assert not report.flagged, report.failures
```

`report.to_dict()` is JSON-serializable. Wrap one judge under several names
(or prompt variants) when you want concordance across prompt wording rather
than across models.

## Disagreement atlas (development only)

**Not included in PyPI 0.3.0.** First follow the
[development checkout instructions](#development-checkout-unreleased-atlas).
The following API and CLI examples require that checkout.

The agreement matrix answers *whether* judges agree. The disagreement atlas
answers *where* they don't — which items drive the split, which judge pairs
diverge together, and which judges are chronically off the panel median.

It builds on an `AgreementMatrixReport` (no re-scoring) or accepts the same
`judges` / `cases` / `rubric` inputs and scores via `agreement_matrix()` first:

```python
from juryrig import MockJudge, agreement_matrix, disagreement_atlas

rubric = "photosynthesis chlorophyll sunlight energy"
judges = [
    MockJudge(name="primary", seed=0),
    MockJudge(name="shadow", seed=1),
    MockJudge(name="audit", seed=2),
]
cases = [
    ("How do plants make food?", "Photosynthesis converts sunlight..."),
    ("Why are leaves green?", "Chlorophyll absorbs red/blue light..."),
]

report = agreement_matrix(judges, cases, rubric, epsilon=0.05)
atlas = disagreement_atlas(report, ranking="variance")  # or "pairwise" / "entropy"

print(atlas.summary())                 # ranked table + clusters + rates
print(atlas.to_markdown(top=5))        # Markdown export
assert atlas.items[0].ranking_score >= atlas.items[-1].ranking_score
for entry in atlas.contrarian:
    print(entry.judge, entry.rate, entry.items)
```

Item ranking metrics:

- **`variance`** — population variance of the panel's scores on that item
- **`pairwise`** — fraction of judge pairs whose scores differ by more than ε
- **`entropy`** — Shannon entropy (bits) of discretized scores (same bucketing
  as Cohen's κ in the agreement matrix)

Ties are broken deterministically: items by ranking score descending then
item index ascending; clusters by size descending then split-pair signature
lexicographically.

`atlas.to_dict()` is JSON-serializable. From the CLI:

```bash
juryrig atlas cases.json --seeds 0,1,2 --ranking pairwise --fmt markdown
juryrig atlas cases.json --seeds 0,1,2 --json
```

## Demo

From a source checkout, after installing it with `python -m pip install -e .`:

```bash
python examples/audit_demo.py
```

For the stable source demo, check out the [`v0.3.0` tag](https://github.com/ianalloway/juryrig/tree/v0.3.0)
in a separate checkout before installing it. The example file is not installed
as a command by the PyPI wheel.

Runs the full audit suite against a fair judge and a rigged one, no API keys
required.

## Design notes

- **Zero runtime dependencies** — stdlib only, including the API clients.
- **Provider-agnostic** — a judge is anything with a `judge()` method; pairwise judges add `compare()`. Protocols, not base classes.
- **Deterministic fixtures** — mock scores use seeded inputs, so audits can be tested without network calls or API keys.
- **Typed** — ships a PEP 561 `py.typed` marker, so the hints reach your type checker.

## License

MIT
