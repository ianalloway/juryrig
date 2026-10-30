"""AnthropicJudge / OpenAIJudge pairwise support — HTTP is mocked throughout."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from juryrig import PairwiseJudge, position_bias
from juryrig.providers import AnthropicJudge, OpenAIJudge

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [("How do plants make food?", "photosynthesis", "plants eat soil")]


def anthropic_payload(content: str) -> dict:
    return {"content": [{"type": "text", "text": content}]}


def openai_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


class ProtocolTest(unittest.TestCase):
    def test_both_providers_are_pairwise_judges(self):
        # Before compare() existed, position_bias could not run against a
        # live model at all — the suite silently skipped its flagship audit.
        self.assertIsInstance(AnthropicJudge(), PairwiseJudge)
        self.assertIsInstance(OpenAIJudge(), PairwiseJudge)


class CompareTest(unittest.TestCase):
    def test_anthropic_compare_parses_the_verdict(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}):
            with mock.patch(
                "juryrig.providers._http_json",
                return_value=anthropic_payload('{"winner": "B", "reasoning": "x"}'),
            ):
                verdict = AnthropicJudge().compare(
                    prompt="p", a="x", b="y", rubric=RUBRIC
                )
        self.assertEqual(verdict, "B")

    def test_openai_compare_parses_the_verdict(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}):
            with mock.patch(
                "juryrig.providers._http_json",
                return_value=openai_payload('{"winner": "tie", "reasoning": "x"}'),
            ):
                verdict = OpenAIJudge().compare(
                    prompt="p", a="x", b="y", rubric=RUBRIC
                )
        self.assertEqual(verdict, "tie")

    def test_compare_sends_the_pairwise_prompt_not_the_scoring_one(self):
        """Both responses must reach the model, or it cannot compare them."""
        captured = {}

        def capture(url, headers, payload, **kw):
            captured.update(payload=payload)
            return openai_payload('{"winner": "A", "reasoning": "x"}')

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}):
            with mock.patch("juryrig.providers._http_json", side_effect=capture):
                OpenAIJudge().compare(
                    prompt="p", a="FIRST", b="SECOND", rubric=RUBRIC
                )

        sent = json.dumps(captured["payload"])
        self.assertIn("RESPONSE_A", sent)
        self.assertIn("RESPONSE_B", sent)
        self.assertIn("FIRST", sent)
        self.assertIn("SECOND", sent)
        self.assertIn("winner", sent)

    def test_missing_key_is_reported_before_any_request(self):
        for judge, var in ((AnthropicJudge(), "ANTHROPIC"), (OpenAIJudge(), "OPENAI")):
            with self.subTest(var=var):
                with mock.patch.dict("os.environ", {}, clear=True):
                    with self.assertRaises(RuntimeError) as caught:
                        judge.compare(prompt="p", a="x", b="y", rubric=RUBRIC)
                self.assertIn(f"{var}_API_KEY", str(caught.exception))

    def test_bad_verdict_is_rejected(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}):
            with mock.patch(
                "juryrig.providers._http_json",
                return_value=openai_payload('{"winner": "C"}'),
            ):
                with self.assertRaises(ValueError):
                    OpenAIJudge().compare(prompt="p", a="x", b="y", rubric=RUBRIC)


class PositionBiasAgainstProviderTest(unittest.TestCase):
    def test_position_bias_now_runs_against_a_provider_judge(self):
        """The whole point: the flagship audit against a live-shaped judge."""
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}):
            with mock.patch(
                "juryrig.providers._http_json",
                return_value=openai_payload('{"winner": "A", "reasoning": "x"}'),
            ):
                report = position_bias(OpenAIJudge(), CASES, RUBRIC)

        # Always answering "A" is pure slot preference — exactly what the
        # audit exists to catch.
        self.assertEqual(report.flips, 1)
        self.assertEqual(report.first_slot_wins, 1.0)
        self.assertTrue(report.flagged)


if __name__ == "__main__":
    unittest.main()
