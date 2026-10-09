"""Optional judge backed by any OpenAI-compatible chat-completions endpoint.

Import directly — not re-exported from `juryrig` (same pattern as providers):

    from juryrig.http_judge import HttpJudge

    judge = HttpJudge(
        url="http://127.0.0.1:11434/v1/chat/completions",  # Ollama, vLLM, …
        model="llama3.2",
    )

Stdlib-only (`urllib`). Point `url` at the full `/v1/chat/completions` path
(or whatever your server exposes). An API key is optional — many local
servers need none. When the server expects `Authorization: Bearer`, pass
`api_key=` or name the env var to read with `api_key_env=`.

`OPENAI_API_KEY` is only picked up implicitly when `url` is
`https://api.openai.com/...`, so pointing `HttpJudge` at a local or
third-party endpoint never sends your OpenAI key there by accident.
"""
from __future__ import annotations

import json
import os
from typing import Mapping
from urllib.parse import urlsplit

from .judge import Judgment, Verdict
from .providers import (
    DEFAULT_RETRY,
    RetryPolicy,
    _http_json,
    _parse_judgment,
    _user_message,
)

_JUDGE_SYSTEM = (
    "You are an impartial evaluator. Score the RESPONSE against the RUBRIC "
    "from 0.0 to 1.0. Reply with JSON only: "
    '{"score": <float>, "reasoning": "<one sentence>"}'
)

_COMPARE_SYSTEM = (
    "You are an impartial evaluator. Compare RESPONSE_A and RESPONSE_B "
    "against the RUBRIC. Reply with JSON only: "
    '{"winner": "A"|"B"|"tie", "reasoning": "<one sentence>"}'
)

_DEFAULT_KEY_ENV = "OPENAI_API_KEY"
_OPENAI_HOST = "api.openai.com"


def _is_openai_url(url: str) -> bool:
    """True only for https://api.openai.com endpoints."""
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() == _OPENAI_HOST


def _compare_user_message(prompt: str, a: str, b: str, rubric: str) -> str:
    return (
        f"PROMPT:\n{prompt}\n\n"
        f"RESPONSE_A:\n{a}\n\n"
        f"RESPONSE_B:\n{b}\n\n"
        f"RUBRIC:\n{rubric}"
    )


def _parse_verdict(text: str) -> Verdict:
    """Extract A/B/tie from a JSON blob that may be wrapped in prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Judge returned non-JSON output: {text[:200]!r}")
    data = json.loads(text[start : end + 1])
    winner = data.get("winner")
    if winner not in ("A", "B", "tie"):
        raise ValueError(
            f"Judge returned winner {winner!r}; expected 'A', 'B', or 'tie'."
        )
    return winner  # type: ignore[return-value]


class HttpJudge:
    """LLM judge over any OpenAI-compatible chat-completions HTTP endpoint.

    Implements both `judge()` (scalar score) and `compare()` (A/B/tie), so the
    full `audit_suite()` — including position bias — can run against a real
    model without MockJudge. Retries use the same `RetryPolicy` as the
    built-in provider judges.

    Auth: an explicit `api_key=` is always sent. Otherwise, if you name an
    env var with `api_key_env=`, its value is sent to `url`. With neither,
    `OPENAI_API_KEY` is used only when `url` is `https://api.openai.com/...`;
    any other endpoint gets no `Authorization` header.
    """

    def __init__(
        self,
        url: str,
        model: str,
        *,
        name: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        headers: Mapping[str, str] | None = None,
        temperature: float = 0.0,
        timeout: float = 60.0,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        if not url or not str(url).strip():
            raise ValueError("url must be a non-empty chat-completions endpoint.")
        if not model or not str(model).strip():
            raise ValueError("model must be a non-empty model id.")
        self.url = str(url).strip()
        self.model = str(model).strip()
        self.name = name or f"http:{self.model}"
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.extra_headers = dict(headers) if headers else {}
        self.temperature = temperature
        self.timeout = timeout
        self.retry = retry

    def _auth_headers(self) -> dict[str, str]:
        if self.api_key is not None:
            key = self.api_key
        elif self.api_key_env is not None:
            # Caller explicitly chose which env var to send to this URL.
            key = os.environ.get(self.api_key_env)
        elif _is_openai_url(self.url):
            key = os.environ.get(_DEFAULT_KEY_ENV)
        else:
            # Never forward OPENAI_API_KEY to an arbitrary endpoint by default.
            key = None
        headers = dict(self.extra_headers)
        if key:
            headers.setdefault("Authorization", f"Bearer {key}")
        return headers

    def _chat(self, *, system: str, user: str) -> str:
        body = _http_json(
            self.url,
            self._auth_headers(),
            {
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
            retry=self.retry,
        )
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                "Chat-completions response missing choices[0].message.content"
            ) from exc

    def judge(self, *, prompt: str, response: str, rubric: str) -> Judgment:
        text = self._chat(
            system=_JUDGE_SYSTEM,
            user=_user_message(prompt, response, rubric),
        )
        return _parse_judgment(text)

    def compare(self, *, prompt: str, a: str, b: str, rubric: str) -> Verdict:
        text = self._chat(
            system=_COMPARE_SYSTEM,
            user=_compare_user_message(prompt, a, b, rubric),
        )
        return _parse_verdict(text)
