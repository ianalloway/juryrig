"""HttpJudge tests — all HTTP is mocked; CI never hits the network."""
from __future__ import annotations

import json
import os
import unittest
import urllib.request
from unittest import mock

from juryrig.http_judge import HttpJudge, _parse_verdict
from juryrig.providers import RetryPolicy


class OkResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def chat_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


class ParseVerdictTest(unittest.TestCase):
    def test_accepts_a_b_or_tie(self):
        for winner in ("A", "B", "tie"):
            with self.subTest(winner=winner):
                self.assertEqual(
                    _parse_verdict(f'{{"winner": "{winner}", "reasoning": "x"}}'),
                    winner,
                )

    def test_tolerates_prose_wrapper(self):
        text = 'Sure.\n{"winner": "B", "reasoning": "clearer"}\nDone.'
        self.assertEqual(_parse_verdict(text), "B")

    def test_rejects_bad_winner(self):
        with self.assertRaises(ValueError):
            _parse_verdict('{"winner": "C", "reasoning": "nope"}')

    def test_rejects_non_json(self):
        with self.assertRaises(ValueError):
            _parse_verdict("A is better")


class HttpJudgeInitTest(unittest.TestCase):
    def test_rejects_empty_url_or_model(self):
        with self.assertRaises(ValueError):
            HttpJudge(url="", model="m")
        with self.assertRaises(ValueError):
            HttpJudge(url="http://x/v1/chat/completions", model="  ")

    def test_default_name_includes_model(self):
        judge = HttpJudge(url="http://localhost/v1/chat/completions", model="llama3.2")
        self.assertEqual(judge.name, "http:llama3.2")


class HttpJudgeMockedHttpTest(unittest.TestCase):
    """Patch urlopen so nothing leaves the process."""

    def setUp(self):
        self.captured: list[urllib.request.Request] = []

    def _install(self, *payloads: dict):
        queue = list(payloads)

        def fake_urlopen(request, timeout=None):
            self.captured.append(request)
            if not queue:
                raise AssertionError("unexpected extra HTTP call")
            return OkResponse(queue.pop(0))

        self._patcher = mock.patch.object(urllib.request, "urlopen", fake_urlopen)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_judge_posts_chat_completions_and_parses_score(self):
        self._install(chat_payload('{"score": 0.8, "reasoning": "covers rubric"}'))
        judge = HttpJudge(
            url="http://127.0.0.1:8080/v1/chat/completions",
            model="local-model",
            api_key="secret-token",
            retry=RetryPolicy(attempts=1),
        )

        judgment = judge.judge(
            prompt="q", response="a good answer", rubric="must be good"
        )

        self.assertEqual(judgment.score, 0.8)
        self.assertEqual(judgment.reasoning, "covers rubric")
        self.assertEqual(len(self.captured), 1)
        req = self.captured[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), "Bearer secret-token")
        body = json.loads(req.data.decode())
        self.assertEqual(body["model"], "local-model")
        self.assertEqual(body["temperature"], 0.0)
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn("RESPONSE", body["messages"][1]["content"])
        self.assertIn("a good answer", body["messages"][1]["content"])

    def test_compare_returns_pairwise_verdict(self):
        self._install(chat_payload('{"winner": "A", "reasoning": "more complete"}'))
        judge = HttpJudge(
            url="http://example.test/v1/chat/completions",
            model="m",
            retry=RetryPolicy(attempts=1),
        )

        verdict = judge.compare(prompt="q", a="strong", b="weak", rubric="r")

        self.assertEqual(verdict, "A")
        body = json.loads(self.captured[0].data.decode())
        self.assertIn("RESPONSE_A", body["messages"][1]["content"])
        self.assertIn("RESPONSE_B", body["messages"][1]["content"])

    def test_api_key_optional_when_absent(self):
        self._install(chat_payload('{"score": 0.5, "reasoning": ""}'))
        # Ensure env cannot sneak a key in.
        with mock.patch.dict(os.environ, {}, clear=True):
            judge = HttpJudge(
                url="http://local/v1/chat/completions",
                model="m",
                retry=RetryPolicy(attempts=1),
            )
            judge.judge(prompt="p", response="r", rubric="rub")

        self.assertIsNone(self.captured[0].get_header("Authorization"))

    def test_api_key_from_env_when_not_passed(self):
        self._install(chat_payload('{"score": 0.1, "reasoning": "x"}'))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "from-env"}):
            judge = HttpJudge(
                url="http://local/v1/chat/completions",
                model="m",
                retry=RetryPolicy(attempts=1),
            )
            judge.judge(prompt="p", response="r", rubric="rub")

        self.assertEqual(
            self.captured[0].get_header("Authorization"), "Bearer from-env"
        )

    def test_custom_headers_merge(self):
        self._install(chat_payload('{"score": 0.2, "reasoning": "x"}'))
        judge = HttpJudge(
            url="http://local/v1/chat/completions",
            model="m",
            api_key="k",
            headers={"X-Custom": "yes"},
            retry=RetryPolicy(attempts=1),
        )
        judge.judge(prompt="p", response="r", rubric="rub")

        req = self.captured[0]
        self.assertEqual(req.get_header("X-custom"), "yes")  # header names fold
        self.assertEqual(req.get_header("Authorization"), "Bearer k")

    def test_malformed_chat_response_raises(self):
        self._install({"choices": []})
        judge = HttpJudge(
            url="http://local/v1/chat/completions",
            model="m",
            retry=RetryPolicy(attempts=1),
        )
        with self.assertRaises(ValueError):
            judge.judge(prompt="p", response="r", rubric="rub")


if __name__ == "__main__":
    unittest.main()
