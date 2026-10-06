# Reproducible synthetic judge evaluation

This experiment exercises juryrig on **12 AI-authored synthetic cases** across
fictional customer support, incident summaries, and research summaries. It is a
controlled demonstration of the toolkit, **not an LLM benchmark**. No real
provider is called and no API key is read by the example.

## Run the stable experiment

The script and dataset live in this source checkout; they are not bundled in the
PyPI wheel. From the repository root, install the stable package in a fresh
virtual environment and run the script:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install "juryrig==0.3.0"
python examples/evaluation_lab.py
python examples/evaluation_lab.py --format json > evaluation.json
```

The default experiment uses only the **stable 0.3.0 APIs**. The script does not
insert the checkout into `sys.path`, so the commands above exercise the installed
package. Avoid setting `PYTHONPATH` when checking the stable wheel.

[Read the measured stable output](evaluation_expected.md). Regenerate it with:

```bash
python examples/evaluation_lab.py > examples/evaluation_expected.md
```

Every run uses seed 0, fresh judges for each group and phase, five consistency
runs, and serial execution. The output records the dataset SHA-256, package
version, configuration overrides, and whether atlas was requested. JSON also
includes thresholds, all agreement scores, item IDs and responses, per-audit
measurements, flagged/skipped audits, and pairwise agreement metrics. The script
exits successfully when the experiment runs: deliberately biased fixtures are
expected to be flagged, so this script is not a production CI pass/fail gate.

## Dataset provenance and construction

[`evaluation_cases.json`](evaluation_cases.json) was created for this example
using an AI coding assistant. It contains no external dataset, customer records,
collected model outputs, or independently collected human judgments. The file
and its provenance are versioned with the example under the repository's MIT
license.

Each of three groups has four cases, a semantic rubric for future real-model
work, and four keyword tokens used by `MockJudge`. Each case has a `candidate`
and a `weak` response. These names describe construction roles, **not validated
human quality labels**. Candidates intentionally cover three of four keyword
tokens, leaving headroom for the verbosity audit rather than saturating at 1.

For each case, the agreement phase scores four variants:

1. The original candidate response.
2. The weak response.
3. The weak response with a fixed judge-targeted injection appended.
4. A non-answer containing all rubric keywords, to expose the baseline's limits.

That makes 16 scored items per group, 48 in total. IDs such as
`return-14/injected_weak` map JSON and atlas output back to the exact fixture.
The injected strings are test data, not instructions to the person or agent
running this experiment.

## What the configurations test

All five configurations use the same `MockJudge` keyword scorer and seed 0;
only the named override changes. They are not independent models.

| Configuration | Override | Question |
| --- | --- | --- |
| baseline | Defaults | Does the control remain invariant to these transformations? |
| slot_first | `position_bias=2.0` | Does swapping A/B order change the preferred content? |
| length_bonus | `verbosity_bias=0.8` | Does irrelevant padding increase the score? |
| injection | `injection_bias=0.6` | Does a weak answer improve when it tells the judge to give full credit? |
| unstable | `instability=0.9` | Does repeating the same input change its score? |

Audits operate on the original candidate/weak pairs. Agreement operates on a
fresh set of judges and all four variants, with ε=0.05 and Cohen's κ scores
rounded to one decimal. The `unstable` configuration can trigger several audits:
score variation can affect padding and injection deltas as well as consistency.
Its call counter is reset between phases; keep this experiment serial.

The committed output shows three useful distinctions:

- The baseline and slot-first judges have identical single-response scores,
  while the slot-first judge flips on every A/B case. Agreement alone misses
  position bias.
- Length bonus passes the within-ε agreement comparison with baseline on these
  short responses, but the padding audit flags it. The transformation exposes
  behavior absent from the original response set.
- The baseline passes all four bias audits yet assigns 1.0 to every
  keyword-stuffed non-answer. Audit success does not establish answer quality.

These are measurements of the deliberately configured fixtures, not estimates
of how often a production judge fails. The groups have matched keyword coverage,
so repeated measurements across groups are not independent replications.

## Optional: inspect the disagreement atlas

Atlas is **unreleased and unavailable in PyPI 0.3.0**. In a separate environment,
install a development checkout that includes atlas, then run:

```bash
python -m pip install -e .
python examples/evaluation_lab.py --atlas
python examples/evaluation_lab.py --atlas --format json > evaluation-atlas.json
```

Markdown adds the five highest-variance items in each group. JSON includes the
full ranking, score splits, clusters, and contrarian rates. Atlas reuses the
agreement score grid without new judge calls. Development currently also reports
version `0.3.0`; the version string alone does not prove atlas is installed.

## Optional: adapt to a real judge later

The CLI intentionally has no live-provider mode. To design a separate real-model
experiment, load a group's `semantic_rubric` instead of its keyword-only mock
rubric, preserve its case IDs, and replace `MockJudge` with your adapter. The
following is configuration only; it does not execute an audit or make a request:

```python
from juryrig.http_judge import HttpJudge

judge = HttpJudge(
    url="http://127.0.0.1:11434/v1/chat/completions",
    model="YOUR_ALREADY_RUNNING_LOCAL_MODEL",
)
# After reviewing the fixtures and runtime, a separate experiment can call
# audit_suite(judge, cases, group["semantic_rubric"]).
```

A real audit requires an available endpoint and makes repeated inference calls;
hosted endpoints may charge. Record endpoint/model revision, prompt template,
sampling settings, retries, and actual request counts separately. Do not compare
such results as if they were this deterministic mock run. No live-model results
are included here.

## Limits

- Small, constructed fixtures do not represent a sampled task distribution.
- Keyword overlap ignores factual truth, negation, policy compliance, and the
  semantic rubric. A high mock score is not an accuracy measurement.
- Shared judge code means agreement is not independent corroboration, and the
  panel median is not ground truth.
- Clipping scores at 0 and 1 can hide bias at the score ceiling. Thresholds and
  κ bucketing affect the summaries; inspect JSON before interpreting a flag.
- No human labels means no human agreement, calibration, or accuracy estimate.
  Establish those with a separate reviewed annotation protocol and held-out data.
