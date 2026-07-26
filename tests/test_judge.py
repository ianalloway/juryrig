import io
import unittest
import urllib.error
import urllib.request

from juryrig.providers import _first_text_block, _http_json, _parse_judgment


class ParseJudgmentTest(unittest.TestCase):
    def test_parses_valid_score(self):
        judgment = _parse_judgment('{"score": 0.75, "reasoning": "ok"}')

        self.assertEqual(judgment.score, 0.75)
        self.assertEqual(judgment.reasoning, "ok")

    def test_rejects_non_finite_json_constants(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _parse_judgment(f'{{"score": {value}, "reasoning": "bad"}}')

    def test_rejects_non_numeric_scores(self):
        for value in ('"NaN"', '"0.8"', "true"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _parse_judgment(f'{{"score": {value}, "reasoning": "bad"}}')

    def test_rejects_out_of_range_scores(self):
        for value in ("-0.1", "1.1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _parse_judgment(f'{{"score": {value}, "reasoning": "bad"}}')


class FirstTextBlockTest(unittest.TestCase):
    def test_skips_leading_non_text_blocks(self):
        blocks = [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": '{"score": 0.5}'},
        ]
        self.assertEqual(_first_text_block(blocks), '{"score": 0.5}')

    def test_raises_when_no_text_block(self):
        with self.assertRaises(ValueError):
            _first_text_block([{"type": "thinking", "thinking": "hmm"}])
        with self.assertRaises(ValueError):
            _first_text_block([])


class HttpErrorTest(unittest.TestCase):
    def test_surfaces_api_error_body(self):
        def raise_http_error(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                url="https://api.example/v1",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"unknown model"}}'),
            )

        original = urllib.request.urlopen
        urllib.request.urlopen = raise_http_error
        try:
            with self.assertRaises(RuntimeError) as caught:
                _http_json("https://api.example/v1", {}, {})
        finally:
            urllib.request.urlopen = original

        message = str(caught.exception)
        self.assertIn("400", message)
        self.assertIn("unknown model", message)


if __name__ == "__main__":
    unittest.main()
