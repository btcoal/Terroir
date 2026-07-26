from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_fundamentals import errors  # noqa: E402
from us_fundamentals.config import load_config  # noqa: E402
from us_fundamentals.errors import ConfigurationError  # noqa: E402
from us_fundamentals.obslog import (  # noqa: E402
    JsonFormatter,
    component_logger,
    log_operation,
)


class ConfigTests(unittest.TestCase):
    def test_development_profile_has_safe_defaults(self) -> None:
        config = load_config("development")
        self.assertEqual(config.profile, "development")
        self.assertIn("@", config.sec.user_agent)
        self.assertLess(config.sec.max_requests_per_second, 10)

    def test_profiles_are_isolated_by_data_root(self) -> None:
        roots = {p: load_config(p).data_root for p in ("development", "test")}
        self.assertNotEqual(roots["development"], roots["test"])

    def test_production_requires_explicit_secrets_via_env(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_config("production")

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_config("staging")


class ErrorTaxonomyTests(unittest.TestCase):
    def test_retryable_and_terminal_are_distinct(self) -> None:
        self.assertFalse(issubclass(errors.RetryableError, errors.TerminalError))
        self.assertFalse(issubclass(errors.TerminalError, errors.RetryableError))

    def test_every_concrete_error_declares_a_category(self) -> None:
        categories = set()
        for name in dir(errors):
            obj = getattr(errors, name)
            if isinstance(obj, type) and issubclass(obj, errors.PipelineError):
                categories.add(obj.category)
        self.assertIn("retryable.rate_limited", categories)
        self.assertIn("terminal.integrity", categories)

    def test_rate_limited_carries_retry_after(self) -> None:
        error = errors.RateLimitedError("slow down", retry_after_seconds=2.5)
        self.assertEqual(error.retry_after_seconds, 2.5)


class StructuredLoggingTests(unittest.TestCase):
    def _capture(self) -> tuple[logging.Logger, io.StringIO]:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger(f"test_component_{id(stream)}")
        logger.handlers[:] = [handler]
        logger.setLevel("INFO")
        logger.propagate = False
        return logger, stream

    def test_log_lines_carry_required_fields(self) -> None:
        base, stream = self._capture()
        logger = component_logger(base.name, "run123", "ds-1")
        with log_operation(logger, "unit_of_work", accession="0000000001-24-000001"):
            pass
        line = json.loads(stream.getvalue())
        for field in (
            "run_id",
            "dataset_version",
            "component",
            "accession",
            "duration_ms",
            "outcome",
        ):
            self.assertIn(field, line, field)
        self.assertEqual(line["outcome"], "ok")

    def test_failures_log_error_category_and_reraise(self) -> None:
        base, stream = self._capture()
        logger = component_logger(base.name, "run123", "ds-1")
        with self.assertRaises(errors.IntegrityError):
            with log_operation(logger, "unit_of_work"):
                raise errors.IntegrityError("hash mismatch")
        line = json.loads(stream.getvalue())
        self.assertEqual(line["outcome"], "error")
        self.assertEqual(line["error_category"], "terminal.integrity")


class CleanCheckoutTests(unittest.TestCase):
    def test_minimal_pipeline_runs_from_documented_command(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "us_fundamentals.jobs.minimal_pipeline"],
            cwd=PROJECT_ROOT,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stderr.strip().splitlines()]
        self.assertEqual(lines[-1]["message"], "pipeline_complete")
        self.assertEqual(lines[-1]["outcome"], "ok")


if __name__ == "__main__":
    unittest.main()
