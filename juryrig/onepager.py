"""One-page report combining the audits a case file supports.

Renders to Markdown (for a PR comment) or a self-contained HTML page (to
share). Nothing is fetched: the HTML carries its own styles, so it opens
offline and has no third-party requests, same as the rest of the library.

Sections the case file cannot support are listed as omitted, with the reason.
An absent section is not a passing one — the same principle as
`AuditSuiteReport.skipped_reasons`.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field


@dataclass
class Section:
    """One audit's contribution to the page."""

    title: str
    flagged: bool
    lines: list[str] = field(default_factory=list)   # pre-formatted text rows
    note: str = ""


@dataclass
class OnePager:
    """A page: the sections that ran, and the ones that could not."""

    judge: str
    sections: list[Section] = field(default_factory=list)
    omitted: dict[str, str] = field(default_factory=dict)

    @property
    def flagged(self) -> bool:
        return any(section.flagged for section in self.sections)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(s.title for s in self.sections if s.flagged)

    def to_markdown(self) -> str:
        verdict = (
            f"**FLAGGED** by: {', '.join(self.failures)}"
            if self.flagged
            else "**PASSED** every audit that ran"
        )
        out = [f"# juryrig report: `{self.judge}`", "", verdict, ""]
        for section in self.sections:
            mark = "❌" if section.flagged else "✅"
            out += [f"## {mark} {section.title}", ""]
            if section.note:
                out += [section.note, ""]
            out += ["```", *section.lines, "```", ""]
        if self.omitted:
            out += ["## Omitted", "",
                    "These audits could not run on this input. "
                    "An omitted audit is not a passing one.", ""]
            out += [f"- **{name}** — {why}" for name, why in self.omitted.items()]
            out += [""]
        return "\n".join(out)

    def to_html(self) -> str:
        # Everything interpolated here comes from a user-supplied case file,
        # so it is escaped: a shared report must not be able to carry script.
        def esc(text: str) -> str:
            return html.escape(str(text), quote=True)

        verdict_class = "bad" if self.flagged else "good"
        verdict = (
            f"FLAGGED by: {esc(', '.join(self.failures))}"
            if self.flagged
            else "PASSED every audit that ran"
        )
        parts = [
            "<!doctype html>",
            '<html lang="en"><head><meta charset="utf-8">',
            f"<title>juryrig report: {esc(self.judge)}</title>",
            "<style>",
            "body{font:14px/1.5 system-ui,sans-serif;max-width:52rem;"
            "margin:2rem auto;padding:0 1rem;color:#111}",
            "h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:1.8rem}",
            "pre{background:#f5f5f5;padding:.75rem;border-radius:4px;"
            "overflow-x:auto}",
            ".verdict{font-weight:600;padding:.5rem .75rem;border-radius:4px}",
            ".good{background:#e6f4ea;color:#11643a}",
            ".bad{background:#fce8e6;color:#8c1d18}",
            ".omitted{color:#555}",
            "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}"
            "pre{background:#1d1d1d}.good{background:#113524;color:#9fe3bd}"
            ".bad{background:#3b1512;color:#f5b3ac}.omitted{color:#aaa}}",
            "</style></head><body>",
            f"<h1>juryrig report: <code>{esc(self.judge)}</code></h1>",
            f'<p class="verdict {verdict_class}">{verdict}</p>',
        ]
        for section in self.sections:
            mark = "❌" if section.flagged else "✅"
            parts.append(f"<h2>{mark} {esc(section.title)}</h2>")
            if section.note:
                parts.append(f"<p>{esc(section.note)}</p>")
            body = "\n".join(esc(line) for line in section.lines)
            parts.append(f"<pre>{body}</pre>")
        if self.omitted:
            parts.append("<h2>Omitted</h2>")
            parts.append(
                '<p class="omitted">These audits could not run on this input. '
                "An omitted audit is not a passing one.</p><ul>"
            )
            for name, why in self.omitted.items():
                parts.append(
                    f'<li class="omitted"><strong>{esc(name)}</strong> '
                    f"— {esc(why)}</li>"
                )
            parts.append("</ul>")
        parts.append("</body></html>")
        return "\n".join(parts)
