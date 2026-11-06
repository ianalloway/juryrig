# JSON report schema

Every `juryrig` subcommand accepts `--json` and prints a single JSON object
to stdout. This document is the contract those objects follow, so CI jobs and
dashboards can read them without breaking on upgrades.

## Versioning

Each object carries two identifying fields:

| Field | Meaning |
|---|---|
| `schema_version` | Integer. The version of this contract. Currently `1`. |
| `report` | Which subcommand produced it: `audit`, `agree`, `atlas`, `calibrate`. |

**`schema_version` is bumped only on a breaking change**: a field removed or
renamed, or its type or meaning changed.

**Adding a field is not a breaking change**, so consumers must ignore keys
they do not recognise. Pin behaviour on `schema_version`, not on the exact
set of keys.

Only the CLI's `--json` output is covered. Python objects such as
`AuditSuiteReport` are ordinary library API and change under the project's
normal semantic versioning. `examples/evaluation_lab.py` emits its own
unrelated `schema_version` for its own format.

## Common fields

`audit` and `calibrate` both carry a `flagged` boolean, which matches the
exit code: `1` when `flagged` is true, `0` when false, `2` on bad input.

## `audit`

```json
{
  "schema_version": 1,
  "report": "audit",
  "judge": "mock",
  "flagged": false,
  "failures": [],
  "skipped": ["position"],
  "skipped_reasons": {"position": "judge has no compare(); ..."},
  "audits": {
    "position": null,
    "verbosity": {"cases": 3, "mean_delta": 0.0, "max_delta": 0.0,
                  "thresholds": {}, "flagged": false},
    "injection": {"...": "..."},
    "consistency": {"...": "..."}
  }
}
```

- `failures` lists the audits that flagged; `flagged` is true when it is
  non-empty.
- `skipped` lists audits that **could not run**, and `skipped_reasons` says
  why for each. A skipped audit is a coverage gap, not a pass — `flagged`
  can be `false` while part of the battery never executed, so check
  `skipped` as well as `flagged`. The CLI also prints a warning to stderr.
- Each entry under `audits` is `null` when that audit was skipped, otherwise
  the audit's own fields plus a derived `flagged`, and `flip_rate` for
  `position`. Each carries the `thresholds` it was judged against, so a
  stored report still explains its own verdict.

## `calibrate`

```json
{
  "schema_version": 1,
  "report": "calibrate",
  "pairs": 8,
  "bins": 5,
  "brier_score": 0.2672,
  "expected_calibration_error": 0.2812,
  "max_ece": 0.1,
  "flagged": true,
  "reliability": [
    {"lower": 0.8, "upper": 1.0, "count": 4,
     "mean_score": 0.875, "accuracy": 0.5, "gap": 0.375}
  ]
}
```

`gap` is `mean_score - accuracy`: positive means overconfident in that
bucket, negative means underconfident. Buckets with no members are omitted.

## `agree` and `atlas`

These wrap `AgreementMatrixReport.to_dict()` and the atlas's `to_dict()`
respectively, under the same two identifying fields. See the README sections
on the agreement matrix and the disagreement atlas for their contents.

## Consuming this safely

```python
import json, subprocess

out = subprocess.run(
    ["juryrig", "cases.json", "--json"], capture_output=True, text=True
)
report = json.loads(out.stdout)

if report["schema_version"] != 1:
    raise SystemExit(f"unsupported schema {report['schema_version']}")

if report["skipped"]:          # a gap is not a pass
    print("not fully audited:", report["skipped_reasons"])
if report["flagged"]:
    print("flagged by:", report["failures"])
```
