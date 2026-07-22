import unittest

from juryrig.providers import _parse_judgment


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


if __name__ == "__main__":
    unittest.main()
