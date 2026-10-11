---
title: juryrig Judge Audit
emoji: ⚖️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
short_description: Audit an LLM judge for position & verbosity bias, offline
tags:
  - llm-as-a-judge
  - evaluation
  - bias
  - calibration
  - position-bias
  - verbosity-bias
  - offline-demo
---

# ⚖️ juryrig Judge Audit

Check an **LLM judge** for **position bias** and **verbosity bias** (plus calibration and cross-judge agreement) using the real
audit functions of [**juryrig**](https://github.com/ianalloway/juryrig). Paste the verdicts or scores your judge already
produced; the Space replays them through juryrig and flags bias against its (deliberately strict) thresholds.

**Offline, zero keys.** No judge API is called and nothing leaves the Space. Live audits that query a judge model are available in
the library and CLI with your own keys.

## What's inside

| Tab | juryrig function | You paste |
|---|---|---|
| One-click demo | `audit_suite` on 5 built-in `MockJudge`s | nothing |
| Position bias | `position_bias` | verdicts for each pair in both orders |
| Verbosity bias | `verbosity_bias` | scores before and after padding |
| Calibration | `brier_score`, `expected_calibration_error`, `reliability_table` | scores + 0/1 human labels |
| Judge agreement | `agreement_matrix` (+ `disagreement_atlas_from_report` when the installed juryrig has it) | one score column per judge |

Every tab has a **Load example** button and a format description. Inputs can be CSV with a header or a JSON list of objects.

### Input formats

Position bias: judge verdict for the same pair shown in both orders (A, B or tie):

```csv
case_id,verdict_original,verdict_swapped,len_first,len_second
q1,A,B,420,380
```

Verbosity bias: score for a response, and for the same response padded with filler:

```csv
case_id,score_original,score_padded
q1,0.62,0.71
```

Calibration: judge score in [0,1] and the human label (1 = good, 0 = bad):

```csv
score,label
0.9,1
```

Agreement: one column per judge:

```csv
case_id,judge_a,judge_b
q1,0.90,0.85
```

`len_first`/`len_second` are optional; they add a simple "does the longer answer win?" statistic that this Space computes itself
(it is not a juryrig audit).

## Run locally

```bash
pip install -r requirements.txt gradio
python app.py
```

## Deploy this Space (maintainers)

1. Create a Space at <https://huggingface.co/new-space> (SDK **Gradio**, CPU basic, public).
2. Upload `README.md`, `app.py` and `requirements.txt` to the Space root (web UI *Files → Add file → Upload files*, or
   `hf upload <your-username>/juryrig-audit . . --repo-type=space`). `ruff.toml` is only for the GitHub repo's CI and can be skipped.
3. No secrets or hardware upgrades are needed. Do not add API keys.
4. Bump `juryrig>=` in `requirements.txt` when a new release ships (the disagreement atlas appears in the release after 0.3.0).

## Links

GitHub: <https://github.com/ianalloway/juryrig> · PyPI: <https://pypi.org/project/juryrig/> · License: MIT
