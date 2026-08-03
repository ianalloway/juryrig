import io
import json
import unittest
import urllib.error
import urllib.request

from juryrig.providers import DEFAULT_RETRY, RetryPolicy, _http_json, _retry_after


def http_error(code, body=b'{"error":"boom"}', headers=None):
    return urllib.error.HTTPError(
        url="https://api.example/v1",
        code=code,
        msg="err",
        hdrs=headers,
        fp=io.BytesIO(body),
    )


class FakeTransport:
    """Stands in for urlopen, replaying a scripted sequence of outcomes."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class OkResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RetryHarness(unittest.TestCase):
    def call(self, transport, retry=None):
        """Run _http_json against a fake transport, recording sleeps."""
        slept = []
        original = urllib.request.urlopen
        urllib.request.urlopen = transport
        try:
            result = _http_json(
                "https://api.example/v1",
                {},
                {},
                retry=retry or DEFAULT_RETRY,
                sleep=slept.append,
            )
        finally:
            urllib.request.urlopen = original
        return result, slept


class RetryPolicyTest(unittest.TestCase):
    def test_delay_grows_and_is_capped(self):
        policy = RetryPolicy(backoff=1.0, max_backoff=4.0)

        self.assertEqual(policy.delay(2), 1.0)
        self.assertEqual(policy.delay(3), 2.0)
        self.assertEqual(policy.delay(4), 4.0)
        self.assertEqual(policy.delay(9), 4.0)   # capped

    def test_rejects_nonsense_policies(self):
        with self.assertRaises(ValueError):
            RetryPolicy(attempts=0)
        with self.assertRaises(ValueError):
            RetryPolicy(backoff=-1)

    def test_retry_after_header_parsed_when_numeric(self):
        numeric = http_error(429, headers={"Retry-After": "7"})
        self.assertEqual(_retry_after(numeric), 7.0)

        # HTTP-date form is not parsed; caller falls back to its own backoff.
        dated = http_error(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28 GMT"})
        self.assertIsNone(_retry_after(dated))
        self.assertIsNone(_retry_after(http_error(429, headers={})))


class TransientFailureTest(RetryHarness):
    def test_succeeds_after_transient_errors(self):
        transport = FakeTransport(
            http_error(503), http_error(429), OkResponse({"ok": True})
        )

        result, slept = self.call(transport)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(transport.calls, 3)
        self.assertEqual(len(slept), 2)

    def test_network_error_is_retried_then_reported(self):
        transport = FakeTransport(
            *(urllib.error.URLError("no route") for _ in range(3))
        )

        with self.assertRaises(RuntimeError) as caught:
            self.call(transport)

        self.assertEqual(transport.calls, 3)
        self.assertIn("unreachable", str(caught.exception))

    def test_gives_up_after_configured_attempts(self):
        transport = FakeTransport(*(http_error(503) for _ in range(5)))

        with self.assertRaises(RuntimeError) as caught:
            self.call(transport, RetryPolicy(attempts=2))

        self.assertEqual(transport.calls, 2)
        self.assertIn("503", str(caught.exception))

    def test_retry_after_overrides_backoff(self):
        transport = FakeTransport(
            http_error(429, headers={"Retry-After": "12"}), OkResponse({"ok": 1})
        )

        _, slept = self.call(transport)

        self.assertEqual(slept, [12.0])


class PermanentFailureTest(RetryHarness):
    def test_client_errors_are_not_retried(self):
        # A bad key or unknown model will fail identically every time;
        # retrying just delays the report and burns quota.
        for code in (400, 401, 403, 404):
            with self.subTest(code=code):
                transport = FakeTransport(http_error(code, b'{"error":"nope"}'))

                with self.assertRaises(RuntimeError) as caught:
                    self.call(transport)

                self.assertEqual(transport.calls, 1)
                self.assertIn(str(code), str(caught.exception))

    def test_error_body_still_surfaces_after_retries(self):
        # Fresh exception per attempt: a real retry gets a new response whose
        # body has not already been consumed.
        transport = FakeTransport(
            *(http_error(503, b'{"error":"overloaded"}') for _ in range(3))
        )

        with self.assertRaises(RuntimeError) as caught:
            self.call(transport)

        self.assertIn("overloaded", str(caught.exception))

    def test_no_retry_policy_means_a_single_attempt(self):
        transport = FakeTransport(http_error(503))

        with self.assertRaises(RuntimeError):
            self.call(transport, RetryPolicy(attempts=1))

        self.assertEqual(transport.calls, 1)


if __name__ == "__main__":
    unittest.main()
