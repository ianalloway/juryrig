"""Optional LLM-backed judges. Not imported by default — import directly:

    from juryrig.providers import AnthropicJudge, OpenAIJudge

Requires ANTHROPIC_API_KEY / OPENAI_API_KEY respectively. Stdlib-only (urllib),
kept out of the core package so `import juryrig` stays minimal.
"""
from __future__ import annotations

import json
import math
import os
import urllib.request

from .judge import Judgment

_JUDGE_INSTRUCTIONS = (
    "You are an impartial evaluator. Score the RESPONSE against the RUBRIC "
    'from 0.0 to 1.0. Reply with JSON only: {"score": <float>, "reasoning": "<one sentence>"}'
)


def _http_json(url: str, headers: dict, payload: dict, timeout: float = 60.0) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as raw:
        return json.loads(raw.read().decode())


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Judge returned invalid JSON numeric constant: {value}")


def _parse_judgment(text: str) -> Judgment:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Judge returned non-JSON output: {text[:200]!r}")
    data = json.loads(text[start : end + 1], parse_constant=_reject_json_constant)
    score = data["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("Judge returned score that is not a JSON number.")
    score = float(score)
    if not math.isfinite(score):
        raise ValueError("Judge returned non-finite score.")
    if not 0.0 <= score <= 1.0:
        raise ValueError("Judge returned score outside the range [0.0, 1.0].")
    return Judgment(
        score=score,
        reasoning=str(data.get("reasoning", "")),
    )


class AnthropicJudge:
    """LLM judge backed by the Anthropic Messages API (ANTHROPIC_API_KEY)."""

    def __init__(self, model: str = "claude-haiku-4-5", name: str | None = None) -> None:
        self.model = model
        self.name = name or f"anthropic:{model}"

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Set ANTHROPIC_API_KEY to use AnthropicJudge.")
        body = _http_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": 200,
                "system": _JUDGE_INSTRUCTIONS,
                "messages": [{
                    "role": "user",
                    "content": f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response}\n\nRUBRIC:\n{rubric}",
                }],
            },
        )
        return _parse_judgment(body["content"][0]["text"])


class OpenAIJudge:
    """LLM judge backed by the OpenAI Chat Completions API (OPENAI_API_KEY)."""

    def __init__(self, model: str = "gpt-4o-mini", name: str | None = None) -> None:
        self.model = model
        self.name = name or f"openai:{model}"

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Set OPENAI_API_KEY to use OpenAIJudge.")
        body = _http_json(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": _JUDGE_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response}\n\nRUBRIC:\n{rubric}",
                    },
                ],
            },
        )
        return _parse_judgment(body["choices"][0]["message"]["content"])
