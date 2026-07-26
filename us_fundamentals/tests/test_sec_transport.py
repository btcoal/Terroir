from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals.config import SecTransportConfig  # noqa: E402
from us_fundamentals.errors import (  # noqa: E402
    ConfigurationError,
    MalformedInputError,
    RateLimitedError,
)
from us_fundamentals.sec_transport import (  # noqa: E402
    CrossProcessRateLimiter,
    SecTransport,
)

CONFIG = SecTransportConfig(
    user_agent="Terroir-test test@example.com",
    max_requests_per_second=8.0,
    max_retries=3,
)


def make_transport(
    handler, tmp: Path, sleeps: list[float] | None = None
) -> SecTransport:
    recorded = sleeps if sleeps is not None else []
    return SecTransport(
        CONFIG,
        cache_dir=tmp,
        transport=httpx.MockTransport(handler),
        sleeper=recorded.append,
    )


class UserAgentTests(unittest.TestCase):
    def test_user_agent_without_contact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigurationError):
                SecTransport(
                    SecTransportConfig(user_agent="just-a-name"),
                    cache_dir=Path(tmp),
                )

    def test_requests_carry_declared_user_agent(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["User-Agent"])
            return httpx.Response(200, content=b"ok")

        with tempfile.TemporaryDirectory() as tmp:
            with make_transport(handler, Path(tmp)) as client:
                client.get("https://www.sec.gov/x")
        self.assertEqual(seen, ["Terroir-test test@example.com"])


class RateLimitTests(unittest.TestCase):
    def test_rate_at_or_above_ten_rps_is_unconfigurable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigurationError):
                CrossProcessRateLimiter(Path(tmp) / "s.json", 10.0)

    def test_aggregate_window_blocks_excess_requests(self) -> None:
        clock = {"now": 0.0}
        sleeps: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock["now"] += seconds

        with tempfile.TemporaryDirectory() as tmp:
            limiter = CrossProcessRateLimiter(
                Path(tmp) / "s.json",
                3.0,
                clock=lambda: clock["now"],
                sleeper=fake_sleep,
            )
            for _ in range(3):
                self.assertEqual(limiter.acquire(), 0.0)
            waited = limiter.acquire()  # fourth within the same second
            self.assertGreater(waited, 0.0)
            self.assertTrue(sleeps)

    def test_window_is_shared_across_instances_like_workers(self) -> None:
        clock = {"now": 0.0}

        def fake_sleep(seconds: float) -> None:
            clock["now"] += seconds

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "s.json"
            first = CrossProcessRateLimiter(
                state, 2.0, clock=lambda: clock["now"], sleeper=fake_sleep
            )
            second = CrossProcessRateLimiter(
                state, 2.0, clock=lambda: clock["now"], sleeper=fake_sleep
            )
            first.acquire()
            first.acquire()
            self.assertGreater(second.acquire(), 0.0)

    def test_429_retry_after_is_honored_then_raises_when_persistent(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "2"})

        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as tmp:
            with make_transport(handler, Path(tmp), sleeps) as client:
                with self.assertRaises(RateLimitedError):
                    client.get("https://www.sec.gov/throttled")
        self.assertIn(2.0, sleeps)


class RetryAndFailureTests(unittest.TestCase):
    def test_transient_503_then_success(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503)
            return httpx.Response(200, content=b"recovered")

        with tempfile.TemporaryDirectory() as tmp:
            with make_transport(handler, Path(tmp)) as client:
                result = client.get("https://www.sec.gov/flaky")
        self.assertEqual(result.content, b"recovered")
        self.assertEqual(result.retries, 2)

    def test_truncated_content_is_retried(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    200, content=b"tru", headers={"Content-Length": "100"}
                )
            return httpx.Response(
                200, content=b"complete", headers={"Content-Length": "8"}
            )

        with tempfile.TemporaryDirectory() as tmp:
            with make_transport(handler, Path(tmp)) as client:
                result = client.get("https://www.sec.gov/partial")
        self.assertEqual(result.content, b"complete")
        self.assertEqual(result.retries, 1)

    def test_malformed_response_is_terminal_not_retried(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(404)

        with tempfile.TemporaryDirectory() as tmp:
            with make_transport(handler, Path(tmp)) as client:
                with self.assertRaises(MalformedInputError):
                    client.get("https://www.sec.gov/gone")
        self.assertEqual(calls["n"], 1)


class CacheTests(unittest.TestCase):
    def test_repeat_request_in_run_is_deduplicated(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, content=b"body", headers={"ETag": '"v1"'})

        with tempfile.TemporaryDirectory() as tmp:
            with make_transport(handler, Path(tmp)) as client:
                first = client.get("https://www.sec.gov/doc")
                second = client.get("https://www.sec.gov/doc")
        self.assertEqual(calls["n"], 1)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(first.sha256, second.sha256)

    def test_restart_revalidates_with_conditional_request(self) -> None:
        conditional_seen: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            inm = request.headers.get("If-None-Match")
            conditional_seen.append(inm)
            if inm == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, content=b"body", headers={"ETag": '"v1"'})

        with tempfile.TemporaryDirectory() as tmp:
            # First "process"
            with make_transport(handler, Path(tmp)) as client:
                client.get("https://www.sec.gov/doc")
            # Restart: new instance, same cache dir
            with make_transport(handler, Path(tmp)) as client:
                result = client.get("https://www.sec.gov/doc")
        self.assertEqual(conditional_seen, [None, '"v1"'])
        self.assertEqual(result.status, 304)
        self.assertTrue(result.from_cache)
        self.assertEqual(result.content, b"body")


class DownloadResumeTests(unittest.TestCase):
    def test_interrupted_bulk_download_resumes_with_range(self) -> None:
        full = b"0123456789" * 100
        ranges_seen: list[str | None] = []
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            ranges_seen.append(request.headers.get("Range"))
            if calls["n"] == 1:
                # Deliver a prefix, then die mid-stream.
                return httpx.Response(200, content=full[:300])
            start = int(ranges_seen[-1].split("=")[1].rstrip("-"))
            return httpx.Response(206, content=full[start:])

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "archive.zip"
            with make_transport(handler, Path(tmp) / "cache") as client:
                client.download_file("https://www.sec.gov/a.zip", out)
                # Simulate interruption: fabricate the partial state the
                # first request would have left behind.
                out.rename(out.with_suffix(".zip.part"))
                client.download_file("https://www.sec.gov/a.zip", out)
            self.assertEqual(out.read_bytes(), full)
        self.assertEqual(ranges_seen[0], None)
        self.assertEqual(ranges_seen[1], "bytes=300-")


if __name__ == "__main__":
    unittest.main()
