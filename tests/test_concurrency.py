import threading
import unittest

from juryrig import Judgment, MockJudge, audit_suite, position_bias, verbosity_bias
from juryrig.audits import _map

RUBRIC = "Answer must mention photosynthesis chlorophyll sunlight energy"
CASES = [
    (f"prompt {i}", f"photosynthesis chlorophyll answer {i}", f"weak {i}")
    for i in range(8)
]


class MapTest(unittest.TestCase):
    def test_preserves_order_regardless_of_workers(self):
        items = list(range(20))

        serial = _map(lambda i: i * 2, items, 1)
        parallel = _map(lambda i: i * 2, items, 8)

        self.assertEqual(serial, parallel)
        self.assertEqual(serial, [i * 2 for i in items])

    def test_serial_mode_spawns_no_threads(self):
        main = threading.current_thread().name

        ran_on = _map(lambda _: threading.current_thread().name, range(3), 1)

        self.assertEqual(ran_on, [main] * 3)

    def test_parallel_mode_actually_uses_threads(self):
        # Counting distinct thread names alone is racy: a task this fast can
        # be finished by the first worker before the pool spins up the rest,
        # yielding one name and a spurious failure. A barrier removes the
        # race — it only clears when 4 calls are genuinely in flight, so 4
        # distinct workers are guaranteed by the time it does.
        barrier = threading.Barrier(4, timeout=5)

        def wait_for_the_others(_):
            barrier.wait()
            return threading.current_thread().name

        ran_on = _map(wait_for_the_others, range(4), 4)

        self.assertEqual(len(ran_on), 4)
        self.assertEqual(len(set(ran_on)), 4)

    def test_rejects_zero_or_negative_workers(self):
        for workers in (0, -1):
            with self.subTest(workers=workers):
                with self.assertRaises(ValueError):
                    _map(lambda i: i, [1], workers)

    def test_exception_propagates(self):
        def boom(i):
            raise RuntimeError("judge exploded")

        for workers in (1, 4):
            with self.subTest(workers=workers):
                with self.assertRaises(RuntimeError):
                    _map(boom, range(4), workers)


class IdenticalResultsTest(unittest.TestCase):
    """Workers are a speed knob, never a correctness one."""

    def test_audit_suite_identical_serial_and_parallel(self):
        rigged = MockJudge(
            name="rigged", position_bias=2.0, verbosity_bias=0.4, injection_bias=0.6
        )
        serial = audit_suite(rigged, CASES, RUBRIC)
        parallel = audit_suite(rigged, CASES, RUBRIC, max_workers=4)

        self.assertEqual(serial.failures, parallel.failures)
        self.assertEqual(serial.verbosity.mean_delta, parallel.verbosity.mean_delta)
        self.assertEqual(serial.injection.max_delta, parallel.injection.max_delta)
        self.assertEqual(serial.position.flips, parallel.position.flips)
        self.assertEqual(
            serial.position.first_slot_wins, parallel.position.first_slot_wins
        )

    def test_individual_audits_identical(self):
        judge = MockJudge(verbosity_bias=0.3)
        pairs = [(p, good) for p, good, _ in CASES]

        self.assertEqual(
            verbosity_bias(judge, pairs, RUBRIC).mean_delta,
            verbosity_bias(judge, pairs, RUBRIC, max_workers=4).mean_delta,
        )
        self.assertEqual(
            position_bias(judge, CASES, RUBRIC).flips,
            position_bias(judge, CASES, RUBRIC, max_workers=4).flips,
        )


class ConcurrentCallTest(unittest.TestCase):
    def test_judge_calls_overlap_when_parallel(self):
        """Prove the work really is concurrent, not just threaded serially."""
        barrier = threading.Barrier(4, timeout=5)

        class BlockingJudge:
            name = "blocking"

            def judge(self, *, prompt, response, rubric):
                # Only passes if 4 calls are in flight at once.
                barrier.wait()
                return Judgment(score=0.5)

        pairs = [(f"p{i}", f"r{i}") for i in range(4)]

        # Two judge() calls per case, so 4 cases keep 4 workers busy.
        report = verbosity_bias(BlockingJudge(), pairs, RUBRIC, max_workers=4)

        self.assertEqual(report.cases, 4)


if __name__ == "__main__":
    unittest.main()
