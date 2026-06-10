import unittest

from juryrig import brier_score, expected_calibration_error, reliability_table


class BrierTest(unittest.TestCase):
    def test_perfect_predictions(self):
        self.assertEqual(brier_score([1.0, 0.0], [1, 0]), 0.0)

    def test_worst_predictions(self):
        self.assertEqual(brier_score([0.0, 1.0], [1, 0]), 1.0)

    def test_known_value(self):
        self.assertAlmostEqual(brier_score([0.8, 0.4], [1, 0]), (0.04 + 0.16) / 2)


class EceTest(unittest.TestCase):
    def test_perfectly_calibrated(self):
        # 0.5-confidence bucket that is right half the time
        scores = [0.5, 0.5, 0.5, 0.5]
        labels = [1, 0, 1, 0]
        self.assertAlmostEqual(expected_calibration_error(scores, labels), 0.0)

    def test_overconfident_judge(self):
        scores = [0.95, 0.95, 0.95, 0.95]
        labels = [1, 0, 0, 0]
        self.assertGreater(expected_calibration_error(scores, labels), 0.5)

    def test_table_includes_score_of_one(self):
        table = reliability_table([1.0], [1], bins=10)
        self.assertEqual(sum(b.count for b in table), 1)


class ValidationTest(unittest.TestCase):
    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            brier_score([0.5], [1, 0])
        with self.assertRaises(ValueError):
            brier_score([], [])
        with self.assertRaises(ValueError):
            brier_score([1.5], [1])
        with self.assertRaises(ValueError):
            brier_score([0.5], [2])


if __name__ == "__main__":
    unittest.main()
