# Changelog

Notable changes to juryrig. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Nothing has been released yet, so everything below is unreleased and the
version in `pyproject.toml` has not moved off `0.1.0`.

## [Unreleased]

### Added

- `audit_suite()` runs every audit against one judge and pools the verdicts
  into an `AuditSuiteReport` (`flagged`, `failures`, `skipped`, `summary()`).
- `juryrig` command-line runner (also `python -m juryrig`): audits a judge
  from a JSON case file, `--json` for machine-readable output. Exits `1` when
  the judge is flagged, `2` on bad input.
- `Thresholds` makes every pass/fail line configurable, per audit or for the
  whole suite. Reports carry the thresholds they were judged against, so a
  stored report still explains its own verdict. Case files accept a
  `"thresholds"` object; unknown keys are rejected rather than ignored.
- `Panel.compare()` pools pairwise A/B votes by majority, returning a
  `PanelVerdict`. An even split reports `winner=None` / `deadlocked=True`
  rather than picking a side.
- `VerbosityBiasReport.max_delta`, matching `PromptInjectionReport`.
- PEP 561 `py.typed` marker, so the package's annotations reach type checkers.
- `PairwiseJudge.compare()` may return `"tie"`. Optional — judges that only
  return `"A"`/`"B"` are unaffected. `position_bias()` treats a consistent tie
  as consistency rather than a flip, treats tie-one-way/pick-the-other as a
  flip, and excludes ties from `first_slot_wins` so a judge that ties
  everything is not reported as maximally slot-biased. The count is exposed
  as `PositionBiasReport.ties`. `Panel.compare()` reports a tie plurality as
  no winner while keeping `agreement` honest.
- `max_workers` on every audit, `audit_suite()`, and the CLI (`--workers`)
  runs judge calls in parallel. Serial by default; results are collected in
  input order, so a report does not depend on the worker count. The judge
  must be thread-safe to raise it.
- Provider judges retry transient HTTP failures (429, 408, 5xx) and network
  errors with exponential backoff, honouring `Retry-After` when the server
  sends a numeric one. Configurable via `RetryPolicy`; client errors such as
  401 and 404 are not retried, since they fail identically every time.

### Changed

- **`audit_suite()` now measures self-consistency on every case and reports
  the least stable one**, rather than only the first. A judge that was steady
  on case 0 and erratic afterwards previously passed this audit clean.
- **Verbosity bias can now flag a judge that previously passed.** A low mean
  delta with one large single-case lift trips `max_delta`, where before only
  the mean was considered.
- CI enforces `ruff check .`, and verifies the built package by installing it
  and running the console script from outside the source tree.

### Fixed

- `expected_calibration_error(..., bins=0)` (or any `bins < 1`) bucketed
  nothing and returned `0.0`, reporting a wildly overconfident judge as
  perfectly calibrated. Now raises `ValueError`.
- Provider HTTP failures discarded the API's error body, leaving only
  `HTTP Error 400: Bad Request`. The body — naming the bad key, unknown
  model, or rate limit — is now surfaced.
- `AnthropicJudge` assumed the first content block was text, which breaks
  when the response leads with a non-text block.

### Breaking

- `VerbosityBiasReport` gained a required `max_delta` field. Code constructing
  the report directly must pass it; the audit functions are unaffected.
- `AuditSuiteReport.summary()` renamed the consistency line's `spread` to
  `worst_spread` and added an `of=<n>` count.

### Known gaps

- `MockJudge`'s `noise` is hash-seeded on `(prompt, response)`, so re-judging
  one input is identical and `self_consistency` always reports a spread of
  `0.0` against it. That is intentional (deterministic tests), but it means
  `MockJudge(noise=...)` cannot demonstrate the consistency audit.
