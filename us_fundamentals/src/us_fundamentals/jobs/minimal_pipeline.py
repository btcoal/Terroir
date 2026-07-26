"""Minimal local pipeline: prove a clean checkout can run end to end.

Runs the two frozen executable policies against their checked-in fixtures
with structured logging. This is the UF-010 smoke pipeline, not a data build.
"""

from __future__ import annotations

import sys
from pathlib import Path

from us_fundamentals.availability import (
    AvailabilityPolicy,
    TradingCalendar,
)
from us_fundamentals.availability import verify_fixture as verify_availability
from us_fundamentals.config import load_config
from us_fundamentals.eligibility import ReleasePolicy
from us_fundamentals.eligibility import verify_fixture as verify_eligibility
from us_fundamentals.obslog import (
    component_logger,
    configure_logging,
    log_operation,
    new_run_id,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    config = load_config()
    configure_logging(config.log_level)
    run_id = new_run_id()
    logger = component_logger("minimal_pipeline", run_id, config.dataset_version)
    failures_total = 0

    with log_operation(logger, "verify_eligibility_policy") as fields:
        policy = ReleasePolicy.from_file(
            PROJECT_ROOT / "config" / "release_1_issuer_universe.json"
        )
        failures = verify_eligibility(
            policy,
            PROJECT_ROOT / "tests" / "fixtures" / "release_1_eligibility_cases.json",
        )
        fields["policy_version"] = policy.policy_version
        fields["failures"] = len(failures)
        failures_total += len(failures)

    with log_operation(logger, "verify_availability_policy") as fields:
        avail = AvailabilityPolicy.from_file(
            PROJECT_ROOT / "config" / "availability_policy.json"
        )
        calendar = TradingCalendar.from_file(
            PROJECT_ROOT / "tests" / "fixtures" / "calendar_2012.json"
        )
        failures = verify_availability(
            avail,
            calendar,
            PROJECT_ROOT / "tests" / "fixtures" / "availability_boundary_cases.json",
        )
        fields["policy_version"] = avail.policy_version
        fields["failures"] = len(failures)
        failures_total += len(failures)

    with log_operation(logger, "pipeline_complete") as fields:
        fields["outcome"] = "ok" if failures_total == 0 else "failed"
    return 0 if failures_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
