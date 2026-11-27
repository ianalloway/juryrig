---
title: juryrig Judge Audit
emoji: ⚖️
colorFrom: indigo
colorTo: blue
sdk: static
app_file: index.html
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
  - pyodide
---

# ⚖️ juryrig Judge Audit (static, runs in your browser)

Check an **LLM judge** for **position bias** and **verbosity bias** (plus calibration and cross-judge agreement) using the real
audit functions of [**juryrig**](https://github.com/ianalloway/juryrig). Paste the verdicts or scores your judge already
produced; the Space replays them through juryrig and flags bias against its (deliberately strict) thresholds.

**Offline, zero keys.** No judge API is called and nothing leaves your browser tab: juryrig runs locally via Pyodide. Live audits that query a judge model are available in
the library and CLI with your own keys.

## What's inside

| Tab | juryrig function | You paste |
|---|---|---|
| One-click demo | `audit_suite` on 5 built-in `MockJudge`s | nothing |
| Position bias | `position_bias` | verdicts for each pair in both orders |
| Verbosity bias | `verbosity_bias` | scores before and after padding |
| Calibration | `brier_score`, `expected_calibration_error`, `reliability_table` | scores + 0/1 human labels |
| Judge agreement | `agreement_matrix` + `disagreement_atlas_from_report` (new in 0.3.1) | one score column per judge |

The one-click demo shows the same pair in both orders and explains why the mock judge picked a different answer. The audit tabs accept CSV with a header or a JSON list of objects. After a run, save a local JSON report with the version, settings, sample size, and derived results. Pasted inputs are excluded, but case IDs and judge names can appear. A passing audit is not evidence of human agreement.

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

### Sample JSON report

After any run, **Download report (JSON)** saves a report like this one (from the one-click demo's built-in mock cases, shortened):

```json
{
  "schema_version": 1,
  "juryrig_version": "0.3.2",
  "audit": "demo",
  "sample_size": 3,
  "settings": { "mock_data": true },
  "results": {
    "judges": [
      ["fair", "0% / 50%", "+0.00", "+0.00", "0.00", "✅ passed"],
      ["slot-biased", "67% / 83%", "+0.00", "+0.00", "0.00", "🚩 position"]
    ],
    "summary": "judge: fair\nposition    flip_rate=0% first_slot_wins=50% ties=0 flagged=False\n…\nPASSED all audits",
    "worked_example": { "prompt": "How do plants make food?", "…": "…" }
  }
}
```

- `schema_version` — version of this report format (currently `1`).
- `juryrig_version` — the juryrig release that produced the results.
- `audit` — which tab ran (`demo`, `position`, `verbosity`, `calibration`, or `agreement`).
- `sample_size` — how many cases the audit ran on.
- `settings` — the thresholds/options in effect for that run.
- `results` — the derived tables and summary text shown on the page; the exact keys depend on the audit.

Pasted inputs are **not** included in the report, but user-supplied case IDs or judge names may appear in `results` (for example in changed-outcome rows), so treat a report from real data as you would the data itself.

## How it works

- `index.html` + `app.js` + `style.css`: plain static page, no build step.
- On load it fetches [Pyodide](https://pyodide.org) (CPython compiled to WebAssembly) from the official jsDelivr CDN,
  then installs the pure-Python `juryrig` wheel from PyPI with `micropip` (pinned: `juryrig==0.3.2`).
- `space.py` holds the same logic as the Gradio version in [`../hf-space/app.py`](../hf-space/app.py), with the gradio UI
  removed; `app.js` calls it through a tiny JSON bridge and renders the results.
- Network: only Pyodide assets (`cdn.jsdelivr.net`) and the wheel (`pypi.org`, `files.pythonhosted.org`). No keys, no server,
  and nothing you type is uploaded. First visit downloads Pyodide (several MB, cached by the browser afterwards).

**Offline wheel (optional fallback):** if PyPI is unreachable, `app.js` first looks next to `index.html`, then tries `wheels/juryrig-0.3.2-py3-none-any.whl`.
Drop that file from `pip download juryrig==0.3.2 --no-deps -d wheels` into a `wheels/` folder to use it.

## Run locally

```bash
cd hf-space-static
python -m http.server 8000   # then open http://localhost:8000
```

(Opening `index.html` straight from disk will not work: browsers block `fetch("space.py")` on `file://`.)

## Deploy this Space (maintainers)

Create a Space with SDK **Static** (free, no hardware) and upload `README.md`, `index.html`, `app.js`, `style.css` and
`space.py` (`ruff.toml` is only for the GitHub repo's CI) to its root. No secrets are needed; do not add API keys. Bump the version pin in `app.js` when a new release ships.

## Links

GitHub: <https://github.com/ianalloway/juryrig> · PyPI: <https://pypi.org/project/juryrig/> · `pip install juryrig` · License: MIT
