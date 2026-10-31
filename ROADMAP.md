# juryrig roadmap

_Last updated 2026-10-31. This is a plan, not a promise. Items move when evidence says they should._

## Where things stand

- **PyPI:** 0.3.1 (2026-10-12): audits, panels, agreement matrix, disagreement atlas, calibration, `HttpJudge` key scoping.
- **Merged on `main` but unreleased:** #38 (judges refuse HTTP redirects so API keys can't leak, SHA-pinned Actions, CodeQL) and #39 (reject NaN/∞ judge scores and audit thresholds). `CHANGELOG.md` `[Unreleased]` does not list them yet.
- **Open PR:** #41 adds provider `compare()`, `verdict_consistency()`, and `juryrig calibrate`.
- **Open issues:** none.

## 0.3.2: security patch (ship first, small)

#38 closes a credential-leak path, so it shouldn't wait for 0.4.0 features.

- [ ] Add #38 and #39 to the CHANGELOG under `[0.3.2]` (Security / Fixed).
- [ ] Bump `pyproject.toml` and `juryrig/__init__.py` to `0.3.2`, then tag and publish.
- [ ] Bump the HF Space pins (`hf-space/`, `hf-space-static/`) to `0.3.2`.

## 0.4.0: "every judge, every audit, from the CLI"

Theme: close the gaps where a headline feature is missing for some judges or can't be reached without writing Python.

### Must have

| # | Item | Why | Source |
|---|---|---|---|
| 1 | Provider `compare()` for `AnthropicJudge` / `OpenAIJudge`, with the pairwise prompt and parser shared with `HttpJudge` | `audit_suite()` currently skips the position audit for the named providers without saying so | #41 |
| 2 | `verdict_consistency()` | Tells run-to-run wavering apart from true position bias. Kept out of `audit_suite()` on purpose (see #41) | #41 |
| 3 | `juryrig calibrate` CLI, with an ECE gate and a per-bucket gap column | Calibration can gate CI like the bias audits do | #41 |
| 4 | `audit_suite()` reports which audits it **skipped** and why, both in the report and as a CLI warning | No more silent coverage gaps (the bug #41 found) | new |
| 5 | Stable JSON report schema, versioned with a `schema_version` field and documented in `docs/report-schema.md` | Lets CI and dashboards consume results without breaking on upgrades | new |

### Should have

| # | Item | Why |
|---|---|---|
| 6 | Rubric-sensitivity audit: paraphrase the rubric and measure score drift | Rubric wording is a hidden degree of freedom in most judge setups |
| 7 | JSONL input and streaming output for `audit` / `agree` / `atlas` | Real eval sets are large, and line-delimited data is what scoring runs emit |
| 8 | Cost and latency accounting per judge (`calls`, `seconds`, optional token counts) in every report | Lets you see what an audit costs before running it on a paid API |
| 9 | Markdown/HTML one-page report (`--fmt html`) that combines suite, atlas, and calibration | Something to drop into a PR comment or share with stakeholders |

### Could have (0.5.0 candidates)

- A pytest plugin (`juryrig.pytest`) exposing a fixture and markers that fail a test when a judge crosses thresholds.
- Async judges (`ajudge` / `acompare`) for high-throughput panels.
- An inter-annotator view that treats human labelers like judges in the agreement matrix and atlas.

### Explicitly out of scope

- Hosting, telemetry, or any network call the user didn't configure.
- Runtime dependencies. juryrig stays zero-dependency, and provider SDKs remain optional.

## Release checklist (0.4.0)

- [ ] All Must-have items merged, with tests offline (mock HTTP only).
- [ ] The evaluation lab's documented numbers are unchanged, or deliberately updated with a note.
- [ ] README capability table updated, and the CHANGELOG `[0.4.0]` section written.
- [ ] Version bumped in both places, tagged, published, and the HF Spaces repinned.

## Triage proposal

There are no open issues to triage today. Proposed label set (none created yet):

| Label | Use |
|---|---|
| `audit` | New or changed bias/consistency audits |
| `provider` | Judge adapters (OpenAI, Anthropic, HTTP) |
| `cli` | `juryrig` command-line modes |
| `report` | Output formats and schema |
| `security` | Key handling, redirects, supply chain |
| `release` | Version bumps, changelog, publishing |
| `0.4.0` | Milestone (better as a GitHub milestone than a label) |

Cleanup suggestions for the existing labels (not applied): `aardvark` and `codex` look like bot or tool labels. Keep them only if an integration uses them. The `invalid` and `wontfix` defaults can stay.

To file as issues once approved, one per row: Must-have items 4 and 5, Should-have items 6 to 9, and the 0.3.2 patch release.
