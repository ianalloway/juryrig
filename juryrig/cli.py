"""Command-line audit runner: `juryrig cases.json`.

Exits non-zero when the judge is flagged, so a CI step is one line.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

from .audits import Thresholds
from .judge import Judge, MockJudge
from .suite import AuditSuiteReport, audit_suite


def _load_thresholds(raw: dict, path: Path) -> Thresholds:
    """Read the optional "thresholds" object, rejecting unknown keys.

    A typo'd key would otherwise be ignored, silently leaving the strict
    default in force while the author believes they loosened it.
    """
    overrides = raw.get("thresholds", {})
    if not isinstance(overrides, dict):
        raise ValueError(f"{path}: 'thresholds' must be an object.")
    known = {f.name for f in fields(Thresholds)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ValueError(
            f"{path}: unknown threshold(s) {', '.join(unknown)}. "
            f"Valid keys: {', '.join(sorted(known))}."
        )
    bad = sorted(
        k
        for k, v in overrides.items()
        if isinstance(v, bool) or not isinstance(v, (int, float))
    )
    if bad:
        raise ValueError(f"{path}: threshold(s) must be numbers: {', '.join(bad)}.")
    return Thresholds(**overrides)


def load_cases(path: Path) -> tuple[str, list[tuple[str, str, str]], Thresholds]:
    """Read a case file: {"rubric": str, "cases": [...], "thresholds": {...}}."""
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object.")

    rubric = raw.get("rubric")
    if not isinstance(rubric, str) or not rubric.strip():
        raise ValueError(f"{path} needs a non-empty string 'rubric'.")

    entries = raw.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} needs a non-empty list 'cases'.")

    cases = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{path} case {i} must be an object.")
        missing = [k for k in ("prompt", "good", "weak") if not entry.get(k)]
        if missing:
            raise ValueError(
                f"{path} case {i} is missing non-empty {', '.join(missing)}."
            )
        cases.append((entry["prompt"], entry["good"], entry["weak"]))
    return rubric, cases, _load_thresholds(raw, path)


def build_judge(provider: str, model: str | None) -> Judge:
    """Instantiate the judge under audit. Providers import lazily."""
    if provider == "mock":
        return MockJudge(name="mock")
    if provider == "anthropic":
        from .providers import AnthropicJudge

        return AnthropicJudge(**({"model": model} if model else {}))
    if provider == "openai":
        from .providers import OpenAIJudge

        return OpenAIJudge(**({"model": model} if model else {}))
    raise ValueError(f"Unknown provider: {provider}")


def report_to_dict(report: AuditSuiteReport) -> dict:
    """JSON-safe view of a suite report, including the derived verdicts."""
    audits = {}
    for name in ("position", "verbosity", "injection", "consistency"):
        sub = getattr(report, name)
        if sub is None:
            audits[name] = None
            continue
        entry = asdict(sub)
        entry["flagged"] = sub.flagged
        if name == "position":
            entry["flip_rate"] = sub.flip_rate
        audits[name] = entry
    return {
        "judge": report.judge,
        "flagged": report.flagged,
        "failures": list(report.failures),
        "skipped": list(report.skipped),
        "audits": audits,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="juryrig",
        description="Audit an LLM judge for position, verbosity, injection, "
        "and consistency flaws. Exits 1 if the judge is flagged.",
    )
    parser.add_argument(
        "cases",
        type=Path,
        help='JSON file: {"rubric": ..., "cases": [{"prompt","good","weak"}, ...]}',
    )
    parser.add_argument(
        "--provider",
        default="mock",
        choices=("mock", "anthropic", "openai"),
        help="Judge to audit (default: mock, no API key needed).",
    )
    parser.add_argument("--model", help="Model id for the chosen provider.")
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Self-consistency repeats (default: 5).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel judge calls (default: 1, serial). Raise this for a "
        "network-backed judge; the judge must be thread-safe.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the report as JSON."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.runs < 1:
        print("juryrig: --runs must be at least 1", file=sys.stderr)
        return 2
    if args.workers < 1:
        print("juryrig: --workers must be at least 1", file=sys.stderr)
        return 2
    try:
        rubric, cases, thresholds = load_cases(args.cases)
        judge = build_judge(args.provider, args.model)
        report = audit_suite(
            judge,
            cases,
            rubric,
            runs=args.runs,
            thresholds=thresholds,
            max_workers=args.workers,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"juryrig: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report_to_dict(report), indent=2))
    else:
        print(report.summary())
    return 1 if report.flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
