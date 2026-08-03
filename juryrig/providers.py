"""Optional LLM-backed judges. Not imported by default — import directly:

    from juryrig.providers import AnthropicJudge, OpenAIJudge

Requires ANTHROPIC_API_KEY / OPENAI_API_KEY respectively. Stdlib-only (urllib),
kept out of the core package so `import juryrig` stays minimal.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .judge import Judgment

# Transient by nature: rate limits, timeouts, and upstream hiccups. Anything
# else (401, 404, 400) means the request itself is wrong and will stay wrong.
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """How hard to try again before giving up on a call.

    An audit is many calls in a row, so one flaky response would otherwise
    throw away every result collected before it.
    """

    attempts: int = 3          # total tries, not retries after the first
    backoff: float = 0.5       # seconds before the 2nd try, doubled each time
    max_backoff: float = 8.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1.")
        if self.backoff < 0 or self.max_backoff < 0:
            raise ValueError("backoff values must be non-negative.")

    def delay(self, attempt: int) -> float:
        """Seconds to wait before `attempt` (1-based, so attempt 2 is first wait)."""
        return min(self.backoff * 2 ** (attempt - 2), self.max_backoff)


DEFAULT_RETRY = RetryPolicy()


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """Honour a server's Retry-After when it gives one, in seconds."""
    raw = getattr(exc, "headers", None)
    value = raw.get("Retry-After") if raw else None
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None  # HTTP-date form; fall back to our own backoff

_JUDGE_INSTRUCTIONS = (
    "You are an impartial evaluator. Score the RESPONSE against the RUBRIC "
    'from 0.0 to 1.0. Reply with JSON only: '
    '{"score": <float>, "reasoning": "<one sentence>"}'
)


def _user_message(prompt: str, response: str, rubric: str) -> str:
    """The graded payload. Identical across providers, so it lives in one place."""
    return f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response}\n\nRUBRIC:\n{rubric}"


def _http_json(
    url: str,
    headers: dict,
    payload: dict,
    timeout: float = 60.0,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep=time.sleep,
) -> dict:
    """POST JSON and return the decoded reply, retrying transient failures."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    for attempt in range(1, retry.attempts + 1):
        last = attempt == retry.attempts
        try:
            with urllib.request.urlopen(request, timeout=timeout) as raw:
                return json.loads(raw.read().decode())
        except urllib.error.HTTPError as exc:
            # The API puts the useful part (bad key, unknown model, rate limit)
            # in the body, which HTTPError's own message drops. Read it once —
            # the stream is not re-readable.
            detail = exc.read().decode(errors="replace").strip()
            if last or exc.code not in _RETRYABLE_STATUSES:
                raise RuntimeError(
                    f"{url} returned HTTP {exc.code}: {detail[:500] or exc.reason}"
                ) from exc
            wait = _retry_after(exc)
            sleep(retry.delay(attempt + 1) if wait is None else wait)
        except urllib.error.URLError as exc:
            # Connection refused, DNS failure, timeout — no status to inspect.
            if last:
                raise RuntimeError(f"{url} unreachable: {exc.reason}") from exc
            sleep(retry.delay(attempt + 1))
    raise AssertionError("unreachable")  # pragma: no cover


def _first_text_block(blocks: list) -> str:
    """Text of the first text block. Anthropic may lead with non-text blocks."""
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            return block["text"]
    raise ValueError("Judge response contained no text block.")


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

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        name: str | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        self.model = model
        self.name = name or f"anthropic:{model}"
        self.retry = retry

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
                    "content": _user_message(prompt, response, rubric),
                }],
            },
            retry=self.retry,
        )
        return _parse_judgment(_first_text_block(body["content"]))


class OpenAIJudge:
    """LLM judge backed by the OpenAI Chat Completions API (OPENAI_API_KEY)."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        name: str | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        self.model = model
        self.name = name or f"openai:{model}"
        self.retry = retry

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
                        "content": _user_message(prompt, response, rubric),
                    },
                ],
            },
            retry=self.retry,
        )
        return _parse_judgment(body["choices"][0]["message"]["content"])
