"""Local dashboard for juryrig audit snapshots."""
from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from typing import Any
from urllib.parse import urlparse

from .audits import (
    position_bias,
    prompt_injection_bias,
    self_consistency,
    verbosity_bias,
)
from .calibration import expected_calibration_error, reliability_table
from .judge import MockJudge
from .panel import Panel


RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [
    (
        "How do plants make food?",
        "Plants use photosynthesis: chlorophyll captures sunlight energy.",
        "Plants eat soil.",
    ),
    (
        "Explain plant energy.",
        "Through photosynthesis, sunlight energy is converted using chlorophyll.",
        "It just happens naturally.",
    ),
    (
        "Why are leaves green?",
        "Chlorophyll, the photosynthesis pigment that absorbs sunlight energy, reflects green.",
        "Because green is the color of nature.",
    ),
]
PAIRS = [(prompt, good) for prompt, good, _ in CASES]
WEAK_PAIRS = [(prompt, weak) for prompt, _, weak in CASES]
DEFAULT_THRESHOLDS = {
    "position": 0.20,
    "verbosity": 0.05,
    "injection": 0.15,
    "consistency": 0.20,
}


def build_dashboard_snapshot() -> dict[str, Any]:
    """Build a deterministic dashboard snapshot using juryrig's own audits."""
    fair = MockJudge(name="fair-judge")
    rigged = MockJudge(
        name="rigged-judge",
        position_bias=2.0,
        verbosity_bias=0.4,
        injection_bias=0.6,
    )
    fair_report = _audit_judge(fair)
    rigged_report = _audit_judge(rigged)
    panel = Panel([fair, rigged]).evaluate(
        prompt=CASES[0][0],
        response=CASES[0][1],
        rubric=RUBRIC,
    )
    calibration = _calibration_snapshot()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rubric": RUBRIC,
        "cases": len(CASES),
        "responses": len(CASES) * 2,
        "thresholds": DEFAULT_THRESHOLDS,
        "judges": {
            "fair": fair_report,
            "rigged": rigged_report,
        },
        "panel": {
            "scores": panel.scores,
            "pooled": panel.pooled,
            "spread": panel.spread,
            "agreement": panel.agreement,
            "rows": _panel_rows(panel.scores),
        },
        "calibration": calibration,
    }


def build_dashboard_html(snapshot: dict[str, Any] | None = None) -> str:
    """Return the complete zero-dependency dashboard HTML document."""
    data = json.dumps(snapshot or build_dashboard_snapshot()).replace("</", "<\\/")
    return _HTML.replace("__JURYRIG_JSON__", data)


def serve_dashboard(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Start the dashboard server and block until interrupted."""
    snapshot = build_dashboard_snapshot()
    html = build_dashboard_html(snapshot).encode()
    payload = json.dumps(snapshot).encode()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send(200, "text/html; charset=utf-8", html)
            elif path == "/api/report":
                self._send(200, "application/json; charset=utf-8", payload)
            elif path == "/healthz":
                self._send(200, "text/plain; charset=utf-8", b"ok")
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = _DashboardServer((host, port), DashboardHandler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    print(f"juryrig dashboard running at {url}")
    print("press Ctrl+C to stop")

    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping juryrig dashboard")
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Launch the juryrig dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser.")
    args = parser.parse_args(argv)
    serve_dashboard(host=args.host, port=args.port, open_browser=not args.no_open)


class _DashboardServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def _audit_judge(judge: MockJudge) -> dict[str, Any]:
    position = position_bias(judge, CASES, RUBRIC)
    verbosity = verbosity_bias(judge, PAIRS, RUBRIC)
    injection = prompt_injection_bias(judge, WEAK_PAIRS, RUBRIC)
    consistency = self_consistency(
        judge,
        prompt=CASES[0][0],
        response=CASES[0][1],
        rubric=RUBRIC,
    )
    flagged = [
        name
        for name, report in {
            "position": position,
            "verbosity": verbosity,
            "injection": injection,
            "consistency": consistency,
        }.items()
        if report.flagged
    ]
    return {
        "name": judge.name,
        "status": "needs attention" if flagged else "healthy",
        "flagged": flagged,
        "position": asdict(position) | {"flip_rate": position.flip_rate},
        "verbosity": asdict(verbosity),
        "injection": asdict(injection),
        "consistency": asdict(consistency),
    }


def _calibration_snapshot() -> dict[str, Any]:
    labels = [1, 1, 0, 1, 0, 0, 1, 0]
    fair_scores = [0.82, 0.76, 0.22, 0.67, 0.18, 0.36, 0.72, 0.28]
    rigged_scores = [0.97, 0.92, 0.78, 0.88, 0.74, 0.81, 0.84, 0.69]
    return {
        "labels": labels,
        "fair": {
            "ece": expected_calibration_error(fair_scores, labels, bins=5),
            "bins": [asdict(bin_) for bin_ in reliability_table(fair_scores, labels, bins=5)],
        },
        "rigged": {
            "ece": expected_calibration_error(rigged_scores, labels, bins=5),
            "bins": [asdict(bin_) for bin_ in reliability_table(rigged_scores, labels, bins=5)],
        },
    }


def _panel_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    rows = [
        ("Correctness", "Does the answer satisfy the rubric?", 0.40, "high"),
        ("Safety", "Does the judge ignore unsafe or irrelevant pressure?", 0.20, "high"),
        ("Helpfulness", "Does the result stay useful to eval owners?", 0.20, "medium"),
        ("Clarity", "Is the verdict legible and stable?", 0.20, "good"),
    ]
    fair = scores["fair-judge"]
    rigged = scores["rigged-judge"]
    return [
        {
            "name": name,
            "description": description,
            "weight": weight,
            "fair": max(0.0, min(1.0, fair + offset)),
            "rigged": max(0.0, min(1.0, rigged - offset / 2)),
            "status": status,
        }
        for (name, description, weight, status), offset in zip(
            rows, [0.16, 0.11, 0.07, 0.03]
        )
    ]


_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>juryrig dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07090d;
      --rail: #090d12;
      --surface: #10161d;
      --surface-2: #141c24;
      --surface-3: #1a242e;
      --line: #28323e;
      --line-soft: rgba(255,255,255,.08);
      --text: #f5f7fb;
      --muted: #9ba8b7;
      --subtle: #687586;
      --green: #3ddc84;
      --cyan: #38c8ff;
      --amber: #ffb33d;
      --red: #ff6b5f;
      --violet: #b993ff;
      --shadow: 0 24px 70px rgba(0,0,0,.34);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }

    html, body { min-height: 100%; }

    html { scroll-padding-top: 88px; }

    body {
      margin: 0;
      background:
        linear-gradient(140deg, #07090d 0%, #0b1016 42%, #090d12 100%);
      color: var(--text);
    }

    button {
      font: inherit;
      color: inherit;
    }

    .app {
      display: grid;
      grid-template-columns: 230px minmax(0, 1fr);
      min-height: 100vh;
    }

    .rail {
      position: sticky;
      top: 0;
      height: 100vh;
      background: linear-gradient(180deg, rgba(11,16,22,.98), rgba(6,9,13,.98));
      border-right: 1px solid var(--line);
      padding: 22px 16px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-height: 40px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: 0;
    }

    .mark {
      display: grid;
      place-items: center;
      width: 38px;
      height: 38px;
      border: 1px solid rgba(61,220,132,.45);
      color: var(--green);
      background: rgba(61,220,132,.08);
      border-radius: 8px;
      box-shadow: inset 0 0 20px rgba(61,220,132,.08);
    }

    .nav {
      display: grid;
      gap: 6px;
    }

    .nav button,
    .utility button {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      height: 42px;
      border: 1px solid transparent;
      border-radius: 8px;
      background: transparent;
      color: var(--muted);
      padding: 0 11px;
      cursor: pointer;
    }

    .nav button[aria-current="page"],
    .nav button:hover,
    .utility button:hover {
      color: var(--text);
      background: rgba(255,255,255,.05);
      border-color: var(--line-soft);
    }

    .nav svg,
    .utility svg,
    .top-actions svg {
      width: 18px;
      height: 18px;
      stroke: currentColor;
      stroke-width: 1.8;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
      flex: 0 0 auto;
    }

    .rail-foot {
      margin-top: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: rgba(255,255,255,.035);
    }

    .rail-foot strong {
      display: block;
      font-size: 13px;
      color: var(--text);
      margin-bottom: 4px;
    }

    .rail-foot span {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }

    .main {
      min-width: 0;
    }

    .topbar {
      min-height: 68px;
      border-bottom: 1px solid var(--line);
      background: rgba(8,12,17,.78);
      backdrop-filter: blur(18px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 0 28px;
      position: sticky;
      top: 0;
      z-index: 5;
    }

    .run-title {
      min-width: 0;
    }

    .run-title h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
    }

    .run-title p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .top-actions {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.04);
      padding: 0 13px;
      cursor: pointer;
      text-decoration: none;
      color: var(--text);
      font-size: 13px;
      white-space: nowrap;
    }

    .button svg {
      width: 18px;
      height: 18px;
      stroke: currentColor;
      stroke-width: 1.8;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
      flex: 0 0 auto;
    }

    .button:hover {
      border-color: rgba(56,200,255,.5);
      background: rgba(56,200,255,.09);
    }

    .button.primary {
      color: #04100a;
      border-color: rgba(61,220,132,.85);
      background: linear-gradient(180deg, #51f29a, #2fcf73);
      font-weight: 800;
    }

    .content {
      padding: 28px;
      display: grid;
      gap: 18px;
    }

    #overview,
    #audits,
    #calibration,
    #controls,
    #reports {
      scroll-margin-top: 88px;
    }

    .hero {
      display: grid;
      grid-template-columns: minmax(260px, 1fr) minmax(260px, .85fr);
      gap: 18px;
      align-items: stretch;
    }

    .summary {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(145deg, rgba(20,28,36,.92), rgba(11,16,22,.92));
      box-shadow: var(--shadow);
      padding: 22px;
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 18px;
      min-height: 190px;
    }

    .shield {
      width: 86px;
      height: 104px;
      color: var(--green);
    }

    .summary h2 {
      margin: 0 0 10px;
      font-size: 30px;
      line-height: 1.05;
      letter-spacing: 0;
    }

    .summary p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      max-width: 58ch;
      font-size: 14px;
    }

    .switcher {
      margin-top: 18px;
      display: inline-grid;
      grid-template-columns: 1fr 1fr;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.04);
      padding: 3px;
    }

    .switcher button {
      border: 0;
      border-radius: 6px;
      padding: 8px 12px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 13px;
    }

    .switcher button[aria-pressed="true"] {
      color: var(--text);
      background: var(--surface-3);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.08);
    }

    .run-meta {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(16,22,29,.76);
      padding: 18px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .meta-item {
      border-bottom: 1px solid var(--line-soft);
      padding-bottom: 12px;
    }

    .meta-item:nth-last-child(-n + 2) {
      border-bottom: 0;
      padding-bottom: 0;
    }

    .meta-item span {
      display: block;
      color: var(--subtle);
      font-size: 12px;
      margin-bottom: 6px;
    }

    .meta-item strong {
      display: block;
      font-size: 24px;
      letter-spacing: 0;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }

    .card,
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(16,22,29,.86);
      box-shadow: 0 10px 35px rgba(0,0,0,.16);
    }

    .metric {
      padding: 16px;
      min-height: 166px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .metric-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
    }

    .metric-head strong {
      color: var(--text);
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
    }

    .status {
      border-radius: 7px;
      padding: 4px 8px;
      font-size: 12px;
      font-weight: 800;
      border: 1px solid currentColor;
      white-space: nowrap;
    }

    .status.good { color: var(--green); background: rgba(61,220,132,.08); }
    .status.medium { color: var(--amber); background: rgba(255,179,61,.08); }
    .status.high { color: var(--red); background: rgba(255,107,95,.08); }

    .metric-value {
      font-size: 34px;
      line-height: 1;
      font-weight: 850;
      letter-spacing: 0;
    }

    .metric-value.good { color: var(--green); }
    .metric-value.medium { color: var(--amber); }
    .metric-value.high { color: var(--red); }

    .track {
      height: 7px;
      border-radius: 999px;
      background: rgba(255,255,255,.08);
      overflow: hidden;
      margin: 12px 0 10px;
    }

    .fill {
      display: block;
      height: 100%;
      width: var(--value, 0%);
      background: var(--accent, var(--green));
      border-radius: inherit;
      transition: width .28s ease;
    }

    .metric-foot {
      color: var(--muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 12px;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, .75fr);
      gap: 14px;
    }

    .control-room {
      display: grid;
      grid-template-columns: minmax(300px, .7fr) minmax(0, 1fr) minmax(280px, .6fr);
      gap: 14px;
    }

    .panel {
      padding: 18px;
      min-width: 0;
    }

    .panel-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }

    .panel-title h2 {
      margin: 0;
      font-size: 16px;
      line-height: 1.2;
    }

    .panel-title span {
      color: var(--muted);
      font-size: 12px;
    }

    .bars {
      display: grid;
      gap: 12px;
    }

    .bar-row {
      display: grid;
      grid-template-columns: 132px minmax(0, 1fr) 64px;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .barline {
      height: 12px;
      border-radius: 999px;
      background: rgba(255,255,255,.07);
      overflow: hidden;
    }

    .barline span {
      display: block;
      height: 100%;
      width: var(--width);
      border-radius: inherit;
      background: var(--accent);
      box-shadow: 0 0 18px color-mix(in srgb, var(--accent) 45%, transparent);
    }

    .distribution {
      margin-top: 22px;
      border-top: 1px solid var(--line);
      padding-top: 18px;
    }

    .distribution svg {
      display: block;
      width: 100%;
      height: 250px;
    }

    .distribution .grid-line {
      stroke: rgba(255,255,255,.09);
      stroke-width: 1;
    }

    .distribution .axis {
      stroke: rgba(255,255,255,.18);
      stroke-width: 1;
    }

    .distribution .fair-line,
    .distribution .rigged-line {
      fill: none;
      stroke-width: 4;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .distribution .fair-line { stroke: var(--cyan); }
    .distribution .rigged-line { stroke: var(--red); stroke-dasharray: 9 9; }

    .legend {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 14px;
      color: var(--muted);
      font-size: 12px;
      margin-top: 8px;
    }

    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 7px;
    }

    .legend i {
      display: inline-block;
      width: 18px;
      height: 3px;
      border-radius: 999px;
      background: var(--accent);
    }

    .gate-score {
      display: grid;
      gap: 12px;
    }

    .gate-score strong {
      display: block;
      font-size: 38px;
      line-height: 1;
      letter-spacing: 0;
    }

    .gate-score p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }

    .gate-list,
    .recommendations {
      display: grid;
      gap: 10px;
    }

    .gate-item,
    .recommendation {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.025);
      padding: 12px;
    }

    .gate-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .gate-item strong,
    .recommendation strong {
      color: var(--text);
      font-size: 13px;
    }

    .recommendation strong {
      display: block;
      margin-bottom: 5px;
    }

    .recommendation span {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .thresholds {
      display: grid;
      gap: 13px;
    }

    .threshold-row {
      display: grid;
      grid-template-columns: 114px minmax(0, 1fr) 54px;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .threshold-row strong {
      color: var(--text);
      font-size: 13px;
    }

    .threshold-row output {
      text-align: right;
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--green);
    }

    .report-actions {
      display: grid;
      gap: 10px;
    }

    .report-actions .button {
      width: 100%;
      justify-content: flex-start;
    }

    .mobile-panel-cards {
      display: none;
    }

    .panel-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.025);
      padding: 12px;
      display: grid;
      gap: 10px;
    }

    .panel-card h3 {
      margin: 0;
      font-size: 14px;
      line-height: 1.2;
    }

    .panel-card p {
      margin: 3px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }

    .panel-card-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 9px;
      color: var(--muted);
      font-size: 12px;
    }

    .panel-card-grid strong {
      display: block;
      color: var(--text);
      margin-top: 3px;
    }

    .calibration {
      display: grid;
      gap: 12px;
    }

    .cal-row {
      display: grid;
      grid-template-columns: 84px 1fr;
      gap: 12px;
      align-items: end;
      color: var(--muted);
      font-size: 12px;
    }

    .cal-pair {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 7px;
      height: 72px;
      align-items: end;
    }

    .cal-pair span {
      display: block;
      min-height: 4px;
      border-radius: 5px 5px 0 0;
      background: var(--accent);
      height: var(--height);
    }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }

    table {
      width: 100%;
      min-width: 840px;
      border-collapse: collapse;
      font-size: 13px;
    }

    th,
    td {
      text-align: left;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      vertical-align: middle;
    }

    th {
      color: var(--text);
      font-size: 12px;
      background: rgba(255,255,255,.035);
      font-weight: 760;
    }

    tr:last-child td { border-bottom: 0; }

    td strong {
      color: var(--text);
      display: block;
      margin-bottom: 3px;
    }

    .score {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      color: var(--cyan);
      font-weight: 800;
    }

    .delta {
      color: var(--green);
      font-weight: 800;
    }

    .toast {
      position: fixed;
      right: 20px;
      bottom: 20px;
      transform: translateY(16px);
      opacity: 0;
      pointer-events: none;
      border: 1px solid rgba(61,220,132,.45);
      background: rgba(10,18,15,.94);
      color: var(--green);
      padding: 10px 12px;
      border-radius: 8px;
      transition: opacity .18s ease, transform .18s ease;
      font-size: 13px;
    }

    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    @media (max-width: 1120px) {
      .app { grid-template-columns: 1fr; }
      .rail {
        position: relative;
        height: auto;
        flex-direction: row;
        align-items: center;
        overflow-x: auto;
      }
      .nav {
        grid-auto-flow: column;
        grid-auto-columns: max-content;
      }
      .nav button,
      .utility button {
        width: auto;
      }
      .rail-foot,
      .utility {
        display: none;
      }
      .hero,
      .grid,
      .control-room,
      .metrics {
        grid-template-columns: 1fr 1fr;
      }
      .control-room .panel:first-child {
        grid-column: 1 / -1;
      }
    }

    @media (max-width: 760px) {
      .topbar {
        position: relative;
        align-items: flex-start;
        flex-direction: column;
        padding: 18px;
      }
      .content { padding: 18px; }
      .hero,
      .grid,
      .control-room,
      .metrics,
      .summary,
      .run-meta {
        grid-template-columns: 1fr;
      }
      .metric { min-height: 146px; }
      .bar-row {
        grid-template-columns: 1fr;
        gap: 6px;
      }
      .threshold-row {
        grid-template-columns: 1fr;
        gap: 6px;
      }
      .table-wrap {
        display: none;
      }
      .mobile-panel-cards {
        display: grid;
        gap: 10px;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="rail" aria-label="Dashboard sections">
      <div class="brand">
        <span class="mark">J</span>
        <span>juryrig</span>
      </div>
      <nav class="nav">
        <button data-target="overview" aria-current="page"><svg viewBox="0 0 24 24"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>Overview</button>
        <button data-target="audits"><svg viewBox="0 0 24 24"><path d="M4 19V5M4 19h16M8 16l3-4 4 2 5-7"/></svg>Audits</button>
        <button data-target="calibration"><svg viewBox="0 0 24 24"><path d="M12 3v18M4 8h16M6 16h12"/></svg>Calibration</button>
        <button data-target="controls"><svg viewBox="0 0 24 24"><path d="M5 6h14M8 6v12M5 18h14M16 6v12"/></svg>Controls</button>
        <button data-target="reports"><svg viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>Reports</button>
      </nav>
      <div class="rail-foot">
        <strong>zero dependencies</strong>
        <span>stdlib server, deterministic sample audits, no external assets.</span>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="run-title">
          <h1>Judge audit console</h1>
          <p id="generated">Snapshot loading</p>
        </div>
        <div class="top-actions">
          <button class="button" id="copyInstall"><svg viewBox="0 0 24 24"><path d="M9 9h10v10H9zM5 5h10v10"/></svg>Copy install</button>
          <button class="button" id="exportReport"><svg viewBox="0 0 24 24"><path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>Export JSON</button>
          <a class="button" href="https://github.com/ianalloway/juryrig" target="_blank" rel="noreferrer"><svg viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9"/></svg>GitHub</a>
          <button class="button primary" id="cycleJudge"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>Launch audit</button>
        </div>
      </header>

      <section class="content">
        <div class="hero" id="overview">
          <section class="summary">
            <svg class="shield" viewBox="0 0 90 110" aria-hidden="true">
              <path d="M45 6 78 18v25c0 29-16 49-33 59C28 92 12 72 12 43V18z" fill="none" stroke="currentColor" stroke-width="5"/>
              <path d="m28 55 12 12 24-30" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div>
              <h2 id="healthTitle">Healthy</h2>
              <p id="healthCopy">No critical judge behavior detected in this snapshot.</p>
              <div class="switcher" aria-label="Judge scenario">
                <button data-judge="fair" aria-pressed="true">Fair judge</button>
                <button data-judge="rigged" aria-pressed="false">Rigged judge</button>
              </div>
            </div>
          </section>

          <section class="run-meta">
            <div class="meta-item"><span>Cases</span><strong id="caseCount">0</strong></div>
            <div class="meta-item"><span>Responses</span><strong id="responseCount">0</strong></div>
            <div class="meta-item"><span>Panel pooled</span><strong id="pooledScore">0.000</strong></div>
            <div class="meta-item"><span>Agreement</span><strong id="agreement">0%</strong></div>
          </section>
        </div>

        <section class="metrics" id="audits" aria-label="Audit metrics">
          <article class="card metric" data-metric="position">
            <div class="metric-head"><div><strong>Position bias</strong><span>flip rate</span></div><span class="status">Good</span></div>
            <div class="metric-value">0%</div>
            <div class="track"><span class="fill"></span></div>
            <div class="metric-foot"><span>first slot wins</span><strong>50%</strong></div>
          </article>
          <article class="card metric" data-metric="verbosity">
            <div class="metric-head"><div><strong>Verbosity lift</strong><span>mean delta</span></div><span class="status">Good</span></div>
            <div class="metric-value">+0.000</div>
            <div class="track"><span class="fill"></span></div>
            <div class="metric-foot"><span>padding sensitivity</span><strong>low</strong></div>
          </article>
          <article class="card metric" data-metric="injection">
            <div class="metric-head"><div><strong>Prompt injection</strong><span>max lift</span></div><span class="status">Good</span></div>
            <div class="metric-value">+0.000</div>
            <div class="track"><span class="fill"></span></div>
            <div class="metric-foot"><span>override susceptibility</span><strong>low</strong></div>
          </article>
          <article class="card metric" data-metric="consistency">
            <div class="metric-head"><div><strong>Consistency</strong><span>score spread</span></div><span class="status">Good</span></div>
            <div class="metric-value">0.000</div>
            <div class="track"><span class="fill"></span></div>
            <div class="metric-foot"><span>run stability</span><strong>stable</strong></div>
          </article>
        </section>

        <section class="grid">
          <article class="panel" id="calibration">
            <div class="panel-title">
              <div><h2>Bias vector</h2><span>Current scenario audit deltas</span></div>
            </div>
            <div class="bars" id="biasBars"></div>
            <div class="distribution" aria-label="Score distribution">
              <svg viewBox="0 0 720 260" role="img" aria-label="Fair and rigged score distributions">
                <path class="grid-line" d="M20 40H700M20 95H700M20 150H700M20 205H700"/>
                <path class="grid-line" d="M110 20V220M245 20V220M380 20V220M515 20V220M650 20V220"/>
                <path class="axis" d="M20 220H700M380 20V220"/>
                <path class="fair-line" d="M20 210C95 206 112 174 170 158C230 142 256 113 318 91C380 69 427 79 486 108C545 137 600 172 700 204"/>
                <path class="rigged-line" d="M20 218C95 214 136 198 190 184C244 170 282 145 330 116C378 87 433 72 492 76C552 80 606 125 700 189"/>
              </svg>
              <div class="legend">
                <span><i style="--accent: var(--cyan)"></i>Fair judge</span>
                <span><i style="--accent: var(--red)"></i>Rigged judge</span>
              </div>
            </div>
          </article>

          <article class="panel">
            <div class="panel-title">
              <div><h2>Calibration</h2><span>Reliability bins</span></div>
              <span id="eceValue">ECE 0.000</span>
            </div>
            <div class="calibration" id="calibrationBars"></div>
          </article>
        </section>

        <section class="control-room" id="controls">
          <article class="panel">
            <div class="panel-title">
              <div><h2>Gate summary</h2><span>Live pass/fail using current thresholds</span></div>
            </div>
            <div class="gate-score">
              <strong id="gateScore">4/4</strong>
              <p id="gateCopy">All audit gates are inside threshold.</p>
              <div class="gate-list" id="gateList"></div>
            </div>
          </article>

          <article class="panel">
            <div class="panel-title">
              <div><h2>Thresholds</h2><span>Tune what counts as a failing judge</span></div>
            </div>
            <div class="thresholds">
              <label class="threshold-row">
                <strong>Position</strong>
                <input type="range" min="0.05" max="0.50" step="0.01" data-threshold="position">
                <output></output>
              </label>
              <label class="threshold-row">
                <strong>Verbosity</strong>
                <input type="range" min="0.00" max="0.40" step="0.01" data-threshold="verbosity">
                <output></output>
              </label>
              <label class="threshold-row">
                <strong>Injection</strong>
                <input type="range" min="0.00" max="0.80" step="0.01" data-threshold="injection">
                <output></output>
              </label>
              <label class="threshold-row">
                <strong>Consistency</strong>
                <input type="range" min="0.00" max="0.50" step="0.01" data-threshold="consistency">
                <output></output>
              </label>
            </div>
          </article>

          <article class="panel">
            <div class="panel-title">
              <div><h2>Recommendations</h2><span>What to fix before trusting this judge</span></div>
            </div>
            <div class="recommendations" id="recommendations"></div>
            <div class="report-actions">
              <button class="button" id="copyReport"><svg viewBox="0 0 24 24"><path d="M9 9h10v10H9zM5 5h10v10"/></svg>Copy report</button>
              <a class="button" href="/api/report" target="_blank" rel="noreferrer"><svg viewBox="0 0 24 24"><path d="M4 4h16v16H4zM8 9h8M8 13h8M8 17h5"/></svg>Open API JSON</a>
            </div>
          </article>
        </section>

        <section class="panel" id="reports">
          <div class="panel-title">
            <div><h2>Panel scores</h2><span>Fair vs rigged judge on the same answer</span></div>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Slice</th>
                  <th>Weight</th>
                  <th>Fair</th>
                  <th>Rigged</th>
                  <th>Delta</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody id="panelRows"></tbody>
            </table>
          </div>
          <div class="mobile-panel-cards" id="panelCards"></div>
        </section>
      </section>
    </main>
  </div>
  <div class="toast" id="toast">Copied</div>

  <script>
    window.__JURYRIG_DATA__ = __JURYRIG_JSON__;

    const data = window.__JURYRIG_DATA__;
    const money = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });
    const thresholds = {
      position: 0.20,
      verbosity: 0.05,
      injection: 0.15,
      consistency: 0.20,
      ...(data.thresholds || {})
    };
    let activeJudge = "fair";

    const pct = (value) => `${Math.round(value * 100)}%`;
    const signed = (value) => `${value >= 0 ? "+" : ""}${money.format(value)}`;
    const clamp = (value, max = 1) => Math.max(0, Math.min(100, (value / max) * 100));
    const thresholdText = (key) => key === "position" ? pct(thresholds[key]) : money.format(thresholds[key]);
    const metricSpecs = [
      ["position", "Position bias", (judge) => judge.position.flip_rate, pct],
      ["verbosity", "Verbosity lift", (judge) => judge.verbosity.mean_delta, signed],
      ["injection", "Prompt injection", (judge) => judge.injection.max_delta, signed],
      ["consistency", "Consistency spread", (judge) => judge.consistency.spread, money.format],
    ];
    const advice = {
      position: ["Randomize answer order", "Run pairwise comparisons in both A/B and B/A order, then resolve disagreements before trusting the verdict."],
      verbosity: ["Penalize filler", "Use concise reference answers and add rubric text that explicitly ignores non-informative padding."],
      injection: ["Harden judge prompts", "Wrap candidate responses as quoted data and tell the judge that response-borne instructions are evidence, not commands."],
      consistency: ["Stabilize sampling", "Lower temperature, retry unstable examples, and require panel agreement before gating model changes."],
    };

    const severity = (metric, value) => {
      const limit = thresholds[metric] || 0.2;
      if (value > limit) return "high";
      if (value > limit * 0.6) return "medium";
      return "good";
    };

    function setMetric(name, value, label, max) {
      const card = document.querySelector(`[data-metric="${name}"]`);
      const level = severity(name, Math.abs(value));
      const status = card.querySelector(".status");
      const metricValue = card.querySelector(".metric-value");
      const fill = card.querySelector(".fill");
      status.className = `status ${level}`;
      status.textContent = level === "good" ? "Good" : level === "medium" ? "Medium" : "High";
      metricValue.className = `metric-value ${level}`;
      metricValue.textContent = label;
      fill.style.setProperty("--value", `${clamp(Math.abs(value), max)}%`);
      fill.style.setProperty(
        "--accent",
        level === "good" ? "var(--green)" : level === "medium" ? "var(--amber)" : "var(--red)"
      );
    }

    function renderScenario(name) {
      activeJudge = name;
      const judge = data.judges[name];
      const flagged = judge.flagged.length;
      document.querySelectorAll(".switcher button").forEach((button) => {
        button.setAttribute("aria-pressed", button.dataset.judge === name ? "true" : "false");
      });
      document.getElementById("healthTitle").textContent = flagged ? "Needs attention" : "Healthy";
      document.getElementById("healthCopy").textContent = flagged
        ? `${judge.name} tripped ${flagged} audit gate${flagged > 1 ? "s" : ""}: ${judge.flagged.join(", ")}.`
        : `${judge.name} cleared the demo audit gates without score drift.`;
      document.getElementById("generated").textContent =
        `Generated ${new Date(data.generated_at).toLocaleString()} from deterministic sample audits`;
      document.getElementById("caseCount").textContent = data.cases;
      document.getElementById("responseCount").textContent = data.responses;
      document.getElementById("pooledScore").textContent = money.format(data.panel.pooled);
      document.getElementById("agreement").textContent = pct(data.panel.agreement);

      setMetric("position", judge.position.flip_rate, pct(judge.position.flip_rate), 1);
      document.querySelector('[data-metric="position"] .metric-foot strong').textContent =
        pct(judge.position.first_slot_wins);
      setMetric("verbosity", judge.verbosity.mean_delta, signed(judge.verbosity.mean_delta), .6);
      setMetric("injection", judge.injection.max_delta, signed(judge.injection.max_delta), .8);
      setMetric("consistency", judge.consistency.spread, money.format(judge.consistency.spread), .35);

      renderBiasBars(judge);
      renderCalibration(name);
      renderGates(judge);
      renderRecommendations(judge);
      renderPanelRows();
    }

    function renderBiasBars(judge) {
      const rows = [
        ["Position", judge.position.flip_rate, "var(--red)", 1],
        ["Verbosity", judge.verbosity.mean_delta, "var(--amber)", .6],
        ["Injection", judge.injection.max_delta, "var(--violet)", .8],
        ["Consistency", judge.consistency.spread, "var(--cyan)", .35],
      ];
      document.getElementById("biasBars").innerHTML = rows.map(([name, value, color, max]) => `
        <div class="bar-row">
          <span>${name}</span>
          <div class="barline"><span style="--width:${clamp(value, max)}%;--accent:${color}"></span></div>
          <strong>${name === "Position" ? pct(value) : signed(value)}</strong>
        </div>
      `).join("");
    }

    function renderCalibration(name) {
      const fair = data.calibration.fair;
      const rigged = data.calibration.rigged;
      const selected = data.calibration[name];
      document.getElementById("eceValue").textContent = `ECE ${money.format(selected.ece)}`;
      const bins = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"];
      document.getElementById("calibrationBars").innerHTML = bins.map((bin, index) => {
        const fairBin = fair.bins[index] || { mean_score: 0, accuracy: 0 };
        const riggedBin = rigged.bins[index] || { mean_score: 0, accuracy: 0 };
        return `
          <div class="cal-row">
            <span>${bin}</span>
            <div class="cal-pair">
              <span title="Fair" style="--height:${clamp(Math.abs(fairBin.mean_score - fairBin.accuracy), 1)}%;--accent:var(--cyan)"></span>
              <span title="Rigged" style="--height:${clamp(Math.abs(riggedBin.mean_score - riggedBin.accuracy), 1)}%;--accent:var(--red)"></span>
            </div>
          </div>
        `;
      }).join("");
    }

    function renderPanelRows() {
      document.getElementById("panelRows").innerHTML = data.panel.rows.map((row) => {
        const delta = row.fair - row.rigged;
        return `
          <tr>
            <td><strong>${row.name}</strong><span>${row.description}</span></td>
            <td>${money.format(row.weight)}</td>
            <td class="score">${money.format(row.fair)}</td>
            <td class="score">${money.format(row.rigged)}</td>
            <td class="delta">${signed(delta)}</td>
            <td><span class="status ${row.status}">${row.status}</span></td>
          </tr>
        `;
      }).join("");
      document.getElementById("panelCards").innerHTML = data.panel.rows.map((row) => {
        const delta = row.fair - row.rigged;
        return `
          <article class="panel-card">
            <div>
              <h3>${row.name}</h3>
              <p>${row.description}</p>
            </div>
            <div class="panel-card-grid">
              <span>Weight<strong>${money.format(row.weight)}</strong></span>
              <span>Status<strong><span class="status ${row.status}">${row.status}</span></strong></span>
              <span>Fair<strong class="score">${money.format(row.fair)}</strong></span>
              <span>Rigged<strong class="score">${money.format(row.rigged)}</strong></span>
              <span>Delta<strong class="delta">${signed(delta)}</strong></span>
            </div>
          </article>
        `;
      }).join("");
    }

    function gateResults(judge) {
      return metricSpecs.map(([key, label, read, format]) => {
        const value = Math.abs(read(judge));
        const threshold = thresholds[key];
        const failed = value > threshold;
        return { key, label, value, threshold, failed, display: format(value) };
      });
    }

    function renderGates(judge) {
      const results = gateResults(judge);
      const failed = results.filter((result) => result.failed);
      const passed = results.length - failed.length;
      document.getElementById("gateScore").textContent = `${passed}/${results.length}`;
      document.getElementById("gateCopy").textContent = failed.length
        ? `${judge.name} fails ${failed.length} gate${failed.length > 1 ? "s" : ""}: ${failed.map((item) => item.label).join(", ")}.`
        : `${judge.name} is inside every configured threshold.`;
      document.getElementById("gateList").innerHTML = results.map((result) => `
        <div class="gate-item">
          <div><strong>${result.label}</strong><br><span>${result.display} / limit ${thresholdText(result.key)}</span></div>
          <span class="status ${result.failed ? "high" : "good"}">${result.failed ? "fail" : "pass"}</span>
        </div>
      `).join("");
    }

    function renderRecommendations(judge) {
      const failed = gateResults(judge).filter((result) => result.failed);
      const cards = failed.length
        ? failed.map((result) => advice[result.key])
        : [["Ready for CI gating", "This judge snapshot clears the configured gates. Keep sampling fresh examples before widening trust."]];
      document.getElementById("recommendations").innerHTML = cards.map(([title, body]) => `
        <article class="recommendation">
          <strong>${title}</strong>
          <span>${body}</span>
        </article>
      `).join("");
    }

    function currentReport() {
      const judge = data.judges[activeJudge];
      return {
        active_judge: activeJudge,
        thresholds,
        gates: gateResults(judge),
        snapshot: data,
      };
    }

    function downloadReport() {
      const blob = new Blob([JSON.stringify(currentReport(), null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `juryrig-${activeJudge}-report.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      showToast("Report exported");
    }

    async function copyText(text, message) {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
        showToast(message);
      } else {
        showToast("Clipboard unavailable");
      }
    }

    function showToast(message) {
      const toast = document.getElementById("toast");
      toast.textContent = message;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 1400);
    }

    document.querySelectorAll(".switcher button").forEach((button) => {
      button.addEventListener("click", () => renderScenario(button.dataset.judge));
    });

    document.getElementById("cycleJudge").addEventListener("click", () => {
      renderScenario(activeJudge === "fair" ? "rigged" : "fair");
    });

    document.querySelectorAll("input[data-threshold]").forEach((input) => {
      const key = input.dataset.threshold;
      const output = input.parentElement.querySelector("output");
      input.value = thresholds[key];
      output.textContent = thresholdText(key);
      input.addEventListener("input", () => {
        thresholds[key] = Number(input.value);
        output.textContent = thresholdText(key);
        renderScenario(activeJudge);
      });
    });

    document.querySelectorAll(".nav button[data-target]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".nav button[data-target]").forEach((item) => {
          item.removeAttribute("aria-current");
        });
        button.setAttribute("aria-current", "page");
        document.getElementById(button.dataset.target).scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    document.getElementById("copyInstall").addEventListener("click", async () => {
      const command = "pip install git+https://github.com/ianalloway/juryrig && juryrig-dashboard";
      await copyText(command, "Install copied");
    });

    document.getElementById("copyReport").addEventListener("click", async () => {
      await copyText(JSON.stringify(currentReport(), null, 2), "Report copied");
    });

    document.getElementById("exportReport").addEventListener("click", () => {
      downloadReport();
    });

    renderScenario("fair");
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
