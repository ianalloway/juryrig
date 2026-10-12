"""juryrig audit workbench: check an LLM judge for position & verbosity bias.

In-browser (Pyodide) build of the Gradio Space logic in ../hf-space/app.py: the
same functions, with the gradio UI replaced by index.html + app.js. Everything runs
locally in your browser tab; no API keys, no server.

Source: https://github.com/ianalloway/juryrig
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

import juryrig
from juryrig import (
    MockJudge,
    Thresholds,
    agreement_matrix,
    audit_suite,
    brier_score,
    expected_calibration_error,
    position_bias,
    reliability_table,
    verbosity_bias,
)
from juryrig.judge import Judgment

try:  # the disagreement atlas ships after juryrig 0.3.0; use it when installed
    from juryrig import disagreement_atlas_from_report
except ImportError:  # pragma: no cover - depends on installed version
    disagreement_atlas_from_report = None

MAX_CHARS = 1_000_000
MAX_ROWS = 5_000
RUBRIC = ""  # replayed judges ignore the rubric



class _GradioShim:
    """Stand-in for the two gradio names the shared logic uses (no gradio in Pyodide)."""

    class Error(Exception):
        pass


gr = _GradioShim()

# --------------------------------------------------------------------------
# Input parsing
# --------------------------------------------------------------------------
class InputError(gr.Error):
    pass


def parse_table(text: str, required: list[str]) -> list[dict[str, str]]:
    """Parse CSV (with header) or a JSON list of objects into row dicts."""
    text = (text or "").strip()
    if not text:
        raise InputError("Paste some data first (or click an example button).")
    if len(text) > MAX_CHARS:
        raise InputError("Input is too large (limit ~1 MB).")
    if text[0] in "[{":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError(f"Invalid JSON: {exc}") from None
        if isinstance(raw, dict):
            raw = raw.get("cases") or raw.get("rows") or raw.get("data")
        if not isinstance(raw, list) or not all(isinstance(r, dict) for r in raw):
            raise InputError("JSON must be a list of objects, e.g. [{...}, {...}].")
        rows = [{str(k).strip().lower(): ("" if v is None else str(v)) for k, v in r.items()} for r in raw]
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise InputError("CSV needs a header row.")
        reader.fieldnames = [(f or "").strip().lower() for f in reader.fieldnames]
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in reader]
    rows = [r for r in rows if any(v.strip() for v in r.values())]
    if not rows:
        raise InputError("No data rows found.")
    if len(rows) > MAX_ROWS:
        raise InputError(f"Too many rows ({len(rows)}); the limit is {MAX_ROWS}.")
    missing = [c for c in required if c not in rows[0]]
    if missing:
        raise InputError(f"Missing column(s): {', '.join(missing)}. Found: {', '.join(rows[0])}.")
    return rows


def to_verdict(value: str, row: int, col: str) -> str:
    v = (value or "").strip().lower()
    if v in ("a", "1", "first"):
        return "A"
    if v in ("b", "2", "second"):
        return "B"
    if v in ("tie", "t", "="):
        return "tie"
    raise InputError(f"Row {row}, column '{col}': expected A, B or tie, got {value!r}.")


def to_float(value: str, row: int, col: str, lo: float | None = None, hi: float | None = None) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise InputError(f"Row {row}, column '{col}': expected a number, got {value!r}.") from None
    if x != x or x in (float("inf"), float("-inf")):
        raise InputError(f"Row {row}, column '{col}': number must be finite.")
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise InputError(f"Row {row}, column '{col}': {x} is outside [{lo}, {hi}].")
    return x


def case_ids(rows: list[dict[str, str]]) -> list[str]:
    ids = [r.get("case_id") or r.get("id") or str(i + 1) for i, r in enumerate(rows)]
    if len(set(ids)) != len(ids):
        raise InputError("case_id values must be unique.")
    return ids


def ok(flag: bool) -> str:
    return "🚩 FLAGGED" if flag else "✅ within thresholds"


# --------------------------------------------------------------------------
# Replay judges: serve recorded outputs through juryrig's judge interfaces
# --------------------------------------------------------------------------
class RecordedPairwiseJudge:
    """PairwiseJudge that replays recorded verdicts for each presentation order."""

    name = "recorded-pairwise"

    def __init__(self, table: dict[str, tuple[str, str]]):
        self.table = table  # case index key -> (verdict_original, verdict_swapped)

    def compare(self, *, prompt: str, a: str, b: str, rubric: str) -> str:
        original, swapped = self.table[prompt]
        return original if a.endswith("::first") else swapped


class RecordedScoreJudge:
    """Judge that replays recorded scores; padded responses get the padded score."""

    def __init__(self, name: str, original: dict[str, float], padded: dict[str, float] | None = None):
        self.name = name
        self.original = original
        self.padded = padded or {}

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        if response == prompt:
            return Judgment(score=self.original[prompt])
        return Judgment(score=self.padded[prompt])


# --------------------------------------------------------------------------
# Example data (built in, one click)
# --------------------------------------------------------------------------
EXAMPLE_POSITION = """case_id,verdict_original,verdict_swapped,len_first,len_second
q1,A,A,420,380
q2,A,A,310,355
q3,A,B,500,210
q4,B,B,260,300
q5,A,A,150,410
q6,A,B,330,325
q7,tie,tie,280,285
q8,A,A,390,350
q9,B,B,200,215
q10,A,A,365,370
"""
EXAMPLE_VERBOSITY = """case_id,score_original,score_padded
q1,0.62,0.71
q2,0.55,0.66
q3,0.70,0.74
q4,0.48,0.60
q5,0.81,0.83
q6,0.58,0.70
"""
EXAMPLE_CALIBRATION = """score,label
0.95,1
0.90,1
0.85,1
0.90,0
0.80,1
0.75,0
0.70,1
0.65,0
0.60,1
0.55,0
0.40,0
0.35,1
0.30,0
0.20,0
0.15,0
0.10,0
"""
EXAMPLE_AGREEMENT = """case_id,judge_a,judge_b,judge_c
q1,0.90,0.85,0.40
q2,0.30,0.35,0.90
q3,0.70,0.72,0.65
q4,0.50,0.95,0.55
q5,0.20,0.25,0.15
q6,0.80,0.40,0.85
q7,0.60,0.62,0.58
q8,0.95,0.90,0.30
"""


# --------------------------------------------------------------------------
# 1) Position bias
# --------------------------------------------------------------------------
@dataclass
class PositionResult:
    report: juryrig.PositionBiasReport
    longer_wins: tuple[int, int] | None  # (longer won, decisive comparisons)


def analyze_position(text: str, flip_limit: float = 0.2, skew_limit: float = 0.2) -> PositionResult:
    rows = parse_table(text, ["verdict_original", "verdict_swapped"])
    ids = case_ids(rows)
    table: dict[str, tuple[str, str]] = {}
    cases = []
    for i, (cid, r) in enumerate(zip(ids, rows), start=1):
        key = f"{i}"
        table[key] = (
            to_verdict(r["verdict_original"], i, "verdict_original"),
            to_verdict(r["verdict_swapped"], i, "verdict_swapped"),
        )
        cases.append((key, f"{key}::first", f"{key}::second"))
    th = Thresholds(position_flip_rate=flip_limit, position_slot_skew=skew_limit)
    report = position_bias(RecordedPairwiseJudge(table), cases, RUBRIC, thresholds=th)

    # Optional extra: does the longer response win more often than not?
    longer = None
    if all("len_first" in r and "len_second" in r and r["len_first"] and r["len_second"] for r in rows):
        won = decisive = 0
        for i, r in enumerate(rows, start=1):
            lf = to_float(r["len_first"], i, "len_first", 0)
            ls = to_float(r["len_second"], i, "len_second", 0)
            verdict = table[str(i)][0]
            if verdict == "tie" or lf == ls:
                continue
            decisive += 1
            won += (verdict == "A") == (lf > ls)
        longer = (won, decisive)
    return PositionResult(report, longer)


def on_position(text, flip_limit, skew_limit):
    r = analyze_position(text, flip_limit, skew_limit)
    p = r.report
    rows = [
        ["Cases", p.cases, ""],
        ["Order flips", f"{p.flips} ({p.flip_rate:.0%})", f"flagged if > {p.thresholds.position_flip_rate:.0%}"],
        ["Share of decisive verdicts won by the FIRST slot", f"{p.first_slot_wins:.0%}",
         f"flagged if |x − 50%| > {p.thresholds.position_slot_skew:.0%}"],
        ["Ties (verdicts with no winner)", p.ties, "excluded from the slot share"],
    ]
    if r.longer_wins is not None:
        won, dec = r.longer_wins
        share = f"{won}/{dec} ({won / dec:.0%})" if dec else "n/a"
        rows.append(["Longer response wins (original order)", share,
                     "extra descriptive stat computed by this Space, not a juryrig audit"])
    head = (f"### Position bias: {ok(p.flagged)}\n\n"
            "A fair judge picks the same *content* in both orders. A **flip** means the slot, not the content, "
            "decided the winner. First-slot share far from 50% means a favourite slot.")
    return head, rows


# --------------------------------------------------------------------------
# 2) Verbosity bias
# --------------------------------------------------------------------------
def analyze_verbosity(text: str, scale_max: float = 1.0, mean_limit: float = 0.05, max_limit: float = 0.15):
    if not scale_max or scale_max <= 0:
        raise InputError("Score scale max must be greater than 0.")
    rows = parse_table(text, ["score_original", "score_padded"])
    ids = case_ids(rows)
    orig, padded, cases = {}, {}, []
    for i, r in enumerate(rows, start=1):
        key = f"{i}"
        orig[key] = to_float(r["score_original"], i, "score_original", 0, scale_max) / scale_max
        padded[key] = to_float(r["score_padded"], i, "score_padded", 0, scale_max) / scale_max
        cases.append((key, key))
    judge = RecordedScoreJudge("recorded", orig, padded)
    th = Thresholds(verbosity_mean_delta=mean_limit, verbosity_max_delta=max_limit)
    report = verbosity_bias(judge, cases, RUBRIC, thresholds=th)
    per_case = [[cid, f"{orig[str(i)]:.3f}", f"{padded[str(i)]:.3f}", f"{padded[str(i)] - orig[str(i)]:+.3f}"]
                for i, cid in enumerate(ids, start=1)]
    return report, per_case


def on_verbosity(text, scale_max, mean_limit, max_limit):
    p, per_case = analyze_verbosity(text, scale_max, mean_limit, max_limit)
    rows = [
        ["Cases", p.cases, ""],
        ["Mean score change after padding", f"{p.mean_delta:+.3f}", f"flagged if > {p.thresholds.verbosity_mean_delta}"],
        ["Largest single-case lift", f"{p.max_delta:+.3f}", f"flagged if > {p.thresholds.verbosity_max_delta}"],
    ]
    head = (f"### Verbosity bias: {ok(p.flagged)}\n\n"
            "Each response was re-scored after appending content-free filler. Filler adds no information, so a "
            "fair judge's score should not rise. A positive mean change means *longer = better* to this judge. "
            "Scores are normalised to 0–1 before the audit.")
    return head, rows, per_case


# --------------------------------------------------------------------------
# 3) Calibration
# --------------------------------------------------------------------------
def analyze_calibration(text: str, bins: int = 5):
    rows = parse_table(text, ["score", "label"])
    scores, labels = [], []
    for i, r in enumerate(rows, start=1):
        scores.append(to_float(r["score"], i, "score", 0, 1))
        lab = to_float(r["label"], i, "label")
        if lab not in (0, 1):
            raise InputError(f"Row {i}, column 'label': expected 0 or 1, got {r['label']!r}.")
        labels.append(int(lab))
    bins = int(bins)
    if bins < 1 or bins > 50:
        raise InputError("Bins must be between 1 and 50.")
    return (brier_score(scores, labels), expected_calibration_error(scores, labels, bins),
            reliability_table(scores, labels, bins), len(scores))


def on_calibration(text, bins):
    brier, ece, table, n = analyze_calibration(text, bins)
    head = (f"### Calibration ({n} labelled judgments)\n\n"
            f"- **Brier score:** {brier:.3f} (lower is better)\n"
            f"- **Expected calibration error:** {ece:.3f} (0 = perfectly calibrated)\n\n"
            "A judge that says 0.9 should be right about 90% of the time. Compare *mean score* with *accuracy* per bin.")
    rows = [[f"{b.lower:.2f}–{b.upper:.2f}", b.count, f"{b.mean_score:.2f}", f"{b.accuracy:.2f}",
             f"{abs(b.mean_score - b.accuracy):.2f}"] for b in table]
    return head, rows


# --------------------------------------------------------------------------
# 4) Agreement (+ disagreement atlas when the installed juryrig has it)
# --------------------------------------------------------------------------
def analyze_agreement(text: str, scale_max: float = 1.0, epsilon: float = 0.05):
    if not scale_max or scale_max <= 0:
        raise InputError("Score scale max must be greater than 0.")
    rows = parse_table(text, [])
    reserved = {"case_id", "id"}
    judges = [c for c in rows[0] if c not in reserved]
    if len(judges) < 2:
        raise InputError("Need at least two judge columns (besides case_id).")
    ids = case_ids(rows)
    keys = [str(i) for i in range(1, len(rows) + 1)]
    recorded = []
    for j in judges:
        scores = {k: to_float(r.get(j, ""), i, j, 0, scale_max) / scale_max
                  for i, (k, r) in enumerate(zip(keys, rows), start=1)}
        recorded.append(RecordedScoreJudge(j, scores))
    report = agreement_matrix(recorded, [(k, k) for k in keys], RUBRIC, epsilon=float(epsilon))
    atlas = disagreement_atlas_from_report(report) if disagreement_atlas_from_report else None
    return report, atlas, ids


def on_agreement(text, scale_max, epsilon):
    report, atlas, ids = analyze_agreement(text, scale_max, epsilon)
    pairs = [[f"{p.judge_a} vs {p.judge_b}", f"{p.within_eps_rate:.0%}", f"{p.kappa:.2f}",
              f"{p.mean_abs_delta:.3f}", ok(p.flagged)] for p in report.pairs]
    head = (f"### Judge agreement: {ok(report.flagged)}\n\n"
            f"{report.cases} items, {len(report.judges)} judges, ε = {report.epsilon:g}. "
            "High agreement on average can hide pairs that rarely agree: the verdict then depends on which judge you picked.")
    if atlas is None:
        atlas_md = ("*Disagreement atlas not available in the installed juryrig version "
                    f"({juryrig.__version__}); it appears in the release after 0.3.0.*")
    else:
        top = [[ids[i.index], f"{i.variance:.3f}", f"{i.pairwise_disagreement:.0%}", ", ".join(sp.replace("|", " × ") for sp in i.split_pairs) or "—"]
               for i in atlas.items[:10]]
        contrarian = ", ".join(f"{c.judge} {c.rate:.0%}" for c in atlas.contrarian)
        atlas_md = ("#### Disagreement atlas: where the panel splits\n\n"
                    + "| item | score variance | pairs beyond ε | splitting pairs |\n|---|---:|---:|---|\n"
                    + "\n".join(f"| {a} | {b} | {c} | {d} |" for a, b, c, d in top)
                    + f"\n\nContrarian rate vs. panel median: {contrarian}")
    return head, pairs, atlas_md


# --------------------------------------------------------------------------
# 5) One-click demo: full audit_suite on built-in mock judges
# --------------------------------------------------------------------------
DEMO_RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
DEMO_CASES = [
    # (prompt, stronger response, weaker-but-plausible response). The pairs are
    # deliberately close so a slot-biased judge has room to be swayed by order.
    ("How do plants make food?",
     "Plants use photosynthesis: chlorophyll captures sunlight energy.",
     "Plants use sunlight energy to make sugar."),
    ("Explain plant energy.",
     "Through photosynthesis, sunlight energy is converted using chlorophyll.",
     "Plants turn sunlight into energy through photosynthesis."),
    ("Why are leaves green?",
     "Chlorophyll, the photosynthesis pigment that absorbs sunlight energy, reflects green.",
     "Leaves look green because chlorophyll reflects green light."),
]


def run_demo():
    judges = [
        MockJudge("fair"),
        MockJudge("slot-biased", position_bias=0.4),
        MockJudge("verbosity-biased", verbosity_bias=0.4),
        MockJudge("injectable", injection_bias=0.5),
        MockJudge("flaky", instability=0.5),
    ]
    reports = [audit_suite(j, DEMO_CASES, DEMO_RUBRIC) for j in judges]
    rows = []
    for rep in reports:
        rows.append([
            rep.judge,
            f"{rep.position.flip_rate:.0%} / {rep.position.first_slot_wins:.0%}" if rep.position else "skipped",
            f"{rep.verbosity.mean_delta:+.2f}",
            f"{rep.injection.mean_delta:+.2f}",
            f"{rep.consistency.spread:.2f}",
            "🚩 " + ", ".join(rep.failures) if rep.flagged else "✅ passed",
        ])
    return rows, "\n\n".join(rep.summary() for rep in reports)


# --------------------------------------------------------------------------
# JS bridge: app.js calls api("<function>", "<json args>") and gets JSON back.
# --------------------------------------------------------------------------
def api(name: str, args_json: str) -> str:
    import json as _json

    if not name.startswith(("on_", "run_demo")):
        return _json.dumps({"ok": False, "error": f"unknown function {name!r}"})
    try:
        result = globals()[name](*_json.loads(args_json))
        return _json.dumps({"ok": True, "result": result}, default=str)
    except gr.Error as exc:
        return _json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # surface unexpected errors in the page instead of the console only
        return _json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
