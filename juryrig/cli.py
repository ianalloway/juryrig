"""Command-line audit runner: `juryrig cases.json`.

Also: `juryrig agree cases.json` for a pairwise concordance matrix across
several judges (or seed variants of MockJudge).

Exits non-zero when the judge / matrix is flagged, so a CI step is one line.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

from .agreement import (
    DEFAULT_AGREEMENT_THRESHOLDS,
    AgreementThresholds,
    agreement_matrix,
)
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


def _load_agreement_thresholds(raw: dict, path: Path) -> AgreementThresholds:
    """Optional ``agreement_thresholds`` object for the concordance audit."""
    overrides = raw.get("agreement_thresholds", {})
    if not overrides:
        return DEFAULT_AGREEMENT_THRESHOLDS
    if not isinstance(overrides, dict):
        raise ValueError(f"{path}: 'agreement_thresholds' must be an object.")
    known = {f.name for f in fields(AgreementThresholds)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ValueError(
            f"{path}: unknown agreement threshold(s) {', '.join(unknown)}. "
            f"Valid keys: {', '.join(sorted(known))}."
        )
    bad = sorted(
        k
        for k, v in overrides.items()
        if isinstance(v, bool) or not isinstance(v, (int, float))
    )
    if bad:
        raise ValueError(
            f"{path}: agreement threshold(s) must be numbers: {', '.join(bad)}."
        )
    return AgreementThresholds(**overrides)


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


def load_agreement_cases(
    path: Path,
) -> tuple[str, list[tuple[str, str]], AgreementThresholds]:
    """Load rubric + (prompt, good) pairs for the agreement-matrix audit."""
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object.")

    rubric, triples, _ = load_cases(path)
    pairs = [(prompt, good) for prompt, good, _ in triples]
    return rubric, pairs, _load_agreement_thresholds(raw, path)


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


class _NamedJudge:
    """Thin rename wrapper so one underlying judge can appear N times."""

    def __init__(self, name: str, inner: Judge) -> None:
        self.name = name
        self._inner = inner

    def judge(self, *, prompt: str, response: str, rubric: str):
        return self._inner.judge(prompt=prompt, response=response, rubric=rubric)


def build_agreement_judges(
    provider: str,
    seeds: list[int],
    names: list[str] | None,
    model: str | None,
) -> list[Judge]:
    """Build N judges for the concordance matrix.

    Mock judges get distinct seeds (and optional names). Live providers
    wrap one model under distinct names — useful for measuring call-to-call
    drift on the same endpoint, not cross-model concordance. Prefer the
    library API when comparing real, different judges.
    """
    if len(seeds) < 2:
        raise ValueError("agreement mode needs at least two --seeds.")
    labels = names if names is not None else [f"judge-{s}" for s in seeds]
    if len(labels) != len(seeds):
        raise ValueError("--names must have the same length as --seeds.")
    if len(set(labels)) != len(labels):
        raise ValueError("Judge names must be unique.")

    if provider == "mock":
        return [
            MockJudge(name=label, seed=seed)
            for label, seed in zip(labels, seeds)
        ]
    inner = build_judge(provider, model)
    return [_NamedJudge(label, inner) for label in labels]


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


def _parse_seeds(raw: str) -> list[int]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) < 2:
        raise ValueError("--seeds needs at least two comma-separated integers.")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError("--seeds must be comma-separated integers.") from exc


def _parse_names(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    names = [p.strip() for p in raw.split(",") if p.strip()]
    if len(names) < 2:
        raise ValueError("--names needs at least two comma-separated labels.")
    return names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="juryrig",
        description="Audit an LLM judge for position, verbosity, injection, "
        "and consistency flaws — or compare several judges with "
        "`juryrig agree`. Exits 1 if flagged.",
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


def build_agree_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="juryrig agree",
        description="Pairwise concordance matrix across N judges scoring the "
        "same items. Exits 1 if any pair is flagged.",
    )
    parser.add_argument(
        "cases",
        type=Path,
        help='JSON case file (uses each case\'s "good" response).',
    )
    parser.add_argument(
        "--provider",
        default="mock",
        choices=("mock", "anthropic", "openai"),
        help="Judge family (default: mock).",
    )
    parser.add_argument("--model", help="Model id for a live provider.")
    parser.add_argument(
        "--seeds",
        default="0,1",
        help="Comma-separated MockJudge seeds / judge slots (default: 0,1).",
    )
    parser.add_argument(
        "--names",
        help="Optional comma-separated judge names matching --seeds.",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=0.05,
        help="Within-ε agreement tolerance on scores (default: 0.05).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel judge calls (default: 1).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the matrix report as JSON."
    )
    parser.add_argument(
        "--fmt",
        choices=("ascii", "markdown"),
        default="ascii",
        help="Matrix table format when not using --json (default: ascii).",
    )
    return parser


def main_audit(argv: list[str]) -> int:
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


def main_agree(argv: list[str]) -> int:
    args = build_agree_parser().parse_args(argv)
    if args.workers < 1:
        print("juryrig: --workers must be at least 1", file=sys.stderr)
        return 2
    if args.epsilon < 0:
        print("juryrig: --epsilon must be non-negative", file=sys.stderr)
        return 2
    try:
        seeds = _parse_seeds(args.seeds)
        names = _parse_names(args.names)
        rubric, cases, thresholds = load_agreement_cases(args.cases)
        judges = build_agreement_judges(
            args.provider, seeds, names, args.model
        )
        report = agreement_matrix(
            judges,
            cases,
            rubric,
            epsilon=args.epsilon,
            thresholds=thresholds,
            max_workers=args.workers,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"juryrig: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary())
        if args.fmt == "markdown":
            print()
            print(report.matrix(metric="within_eps", fmt="markdown"))
    return 1 if report.flagged else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "agree":
        return main_agree(argv[1:])
    return main_audit(argv)


if __name__ == "__main__":
    raise SystemExit(main())
