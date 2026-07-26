"""Executable information-availability and execution-eligibility policy.

Gold availability answers when a filing became publicly knowable. Research
eligibility answers when the default daily policy would first allow execution.
This module keeps the two computations separate and never lets an execution
rule feed back into an information time.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


class AvailabilityPolicyError(ValueError):
    """Raised when a policy or calendar file violates its contract."""


class AvailabilityRecordError(ValueError):
    """Raised when a filing record cannot be classified."""


@dataclass(frozen=True)
class Session:
    session_date: date
    open_at: datetime
    close_at: datetime
    kind: str


@dataclass(frozen=True)
class TradingCalendar:
    """A versioned session calendar with explicit non-session entries."""

    calendar_id: str
    calendar_version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    weekend_days: frozenset[int]
    sessions: Mapping[date, Session]
    non_sessions: Mapping[date, str]

    @classmethod
    def from_file(cls, path: str | Path) -> TradingCalendar:
        with Path(path).open(encoding="utf-8") as calendar_file:
            payload = json.load(calendar_file)
        tz_name = payload.get("exchange_timezone")
        if not isinstance(tz_name, str):
            raise AvailabilityPolicyError("calendar must declare exchange_timezone")
        tz = ZoneInfo(tz_name)
        coverage = payload.get("coverage", {})
        sessions: dict[date, Session] = {}
        for row in payload.get("sessions", []):
            session_date = date.fromisoformat(row["session_date"])
            sessions[session_date] = Session(
                session_date=session_date,
                open_at=_local(session_date, row["open_local"], tz),
                close_at=_local(session_date, row["close_local"], tz),
                kind=row["kind"],
            )
        non_sessions = {
            date.fromisoformat(row["date"]): row["kind"]
            for row in payload.get("non_sessions", [])
        }
        calendar = cls(
            calendar_id=payload.get("calendar_id", "<unknown>"),
            calendar_version=payload.get("calendar_version", "<unknown>"),
            timezone=tz_name,
            coverage_start=date.fromisoformat(coverage["start"]),
            coverage_end=date.fromisoformat(coverage["end"]),
            weekend_days=frozenset(payload.get("weekend_days", [5, 6])),
            sessions=sessions,
            non_sessions=non_sessions,
        )
        calendar._validate()
        return calendar

    def _validate(self) -> None:
        day = self.coverage_start
        while day <= self.coverage_end:
            if day.weekday() not in self.weekend_days:
                if day not in self.sessions and day not in self.non_sessions:
                    raise AvailabilityPolicyError(
                        f"calendar has no entry for weekday {day.isoformat()}; "
                        "a missing weekday must be an explicit non-session"
                    )
            day += timedelta(days=1)

    def _require_covered(self, instant: datetime) -> None:
        local_date = instant.astimezone(ZoneInfo(self.timezone)).date()
        if not (self.coverage_start <= local_date <= self.coverage_end):
            raise AvailabilityRecordError(
                f"{instant.isoformat()} is outside calendar coverage "
                f"{self.coverage_start}..{self.coverage_end}"
            )

    def session_on(self, instant: datetime) -> Session | None:
        """The session on the instant's local exchange date, if one exists."""
        self._require_covered(instant)
        local_date = instant.astimezone(ZoneInfo(self.timezone)).date()
        return self.sessions.get(local_date)

    def next_session_after(self, instant: datetime) -> Session:
        """The first session whose open is strictly after the instant."""
        self._require_covered(instant)
        local_date = instant.astimezone(ZoneInfo(self.timezone)).date()
        day = local_date
        while day <= self.coverage_end:
            session = self.sessions.get(day)
            if session is not None and session.open_at > instant:
                return session
            day += timedelta(days=1)
        raise AvailabilityRecordError(
            f"no session after {instant.isoformat()} within calendar coverage"
        )


@dataclass(frozen=True)
class AvailabilityPolicy:
    """Validated availability policy shared by backfill and live ingestion."""

    policy_id: str
    policy_version: str
    dissemination_buffer: timedelta
    backfill_confidence: str
    methods: frozenset[str]
    confidence_levels: frozenset[str]
    default_execution_policy_id: str
    intra_session_information_accepted: bool
    processing_latency: timedelta

    @classmethod
    def from_file(cls, path: str | Path) -> AvailabilityPolicy:
        with Path(path).open(encoding="utf-8") as policy_file:
            payload = json.load(policy_file)
        backfill = payload.get("backfill", {})
        research = payload.get("research_contract", {})
        daily = research.get("default_daily_policy", {})
        if backfill.get("method") != "acceptance_plus_buffer":
            raise AvailabilityPolicyError(
                "backfill.method must be acceptance_plus_buffer"
            )
        buffer_seconds = backfill.get("dissemination_buffer_seconds")
        if not isinstance(buffer_seconds, (int, float)) or buffer_seconds < 0:
            raise AvailabilityPolicyError(
                "backfill.dissemination_buffer_seconds must be non-negative"
            )
        if research.get("intraday_requires_explicit_latency") is not True:
            raise AvailabilityPolicyError(
                "research_contract.intraday_requires_explicit_latency must be true"
            )
        edgar = payload.get("edgar", {})
        if edgar.get("rollover_affects_information_availability") is not False:
            raise AvailabilityPolicyError(
                "the 17:30 filing-date rollover must not affect availability"
            )
        return cls(
            policy_id=payload["policy_id"],
            policy_version=payload["policy_version"],
            dissemination_buffer=timedelta(seconds=buffer_seconds),
            backfill_confidence=backfill.get("confidence", "modeled"),
            methods=frozenset(payload["availability_methods"]),
            confidence_levels=frozenset(payload["availability_confidence_levels"]),
            default_execution_policy_id=daily.get("policy_id", "daily_next_open"),
            intra_session_information_accepted=bool(
                daily.get("intra_session_information_accepted", False)
            ),
            processing_latency=timedelta(
                seconds=daily.get("processing_latency_seconds", 0)
            ),
        )

    def compute_availability(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Derive Gold availability fields for one filing record."""
        method = record.get("availability_method", "acceptance_plus_buffer")
        if method not in self.methods:
            raise AvailabilityRecordError(f"unknown availability_method {method!r}")

        acceptance = _aware_required(record, "sec_acceptance_datetime")
        observed = _aware_optional(record, "observed_first_seen_at")

        if method == "observed_dissemination":
            if observed is None:
                raise AvailabilityRecordError(
                    "observed_dissemination requires observed_first_seen_at"
                )
            available_at, confidence = observed, "exact"
        elif method == "manual_evidence":
            manual = _aware_required(record, "manual_available_at")
            available_at, confidence = manual, "exact"
        else:  # acceptance_plus_buffer
            available_at = acceptance + self.dissemination_buffer
            confidence = self.backfill_confidence

        return {
            "sec_acceptance_datetime": acceptance.isoformat(),
            "information_available_at": available_at.isoformat(),
            "observed_first_seen_at": observed.isoformat() if observed else None,
            "availability_method": method,
            "availability_policy_version": self.policy_version,
            "availability_confidence": confidence,
        }

    def compute_eligibility(
        self, available_at: datetime, calendar: TradingCalendar
    ) -> dict[str, Any]:
        """Apply the default daily execution policy to an availability time.

        `eligible_at_open` / `eligible_at_close` describe the session on the
        availability date (information facts). `eligible_session` is where the
        default next-open policy first allows execution.
        """
        effective = available_at + self.processing_latency
        same_day = calendar.session_on(effective)
        if same_day is None:
            eligible = calendar.next_session_after(effective)
            at_open = at_close = False
        else:
            at_open = effective < same_day.open_at
            at_close = effective < same_day.close_at
            if at_open:
                eligible = same_day
            else:
                # Information arriving intra-session or later defers to the
                # next open under the default daily policy.
                eligible = calendar.next_session_after(effective)
        return {
            "eligible_session": eligible.session_date.isoformat(),
            "eligible_at_open": at_open,
            "eligible_at_close": at_close,
            "execution_policy_version": (
                f"{self.default_execution_policy_id}/{self.policy_version}"
            ),
            "calendar_version": f"{calendar.calendar_id}/{calendar.calendar_version}",
        }

    def classify(
        self, record: Mapping[str, Any], calendar: TradingCalendar
    ) -> dict[str, Any]:
        gold = self.compute_availability(record)
        research = self.compute_eligibility(
            datetime.fromisoformat(gold["information_available_at"]), calendar
        )
        return {"gold": gold, "research": research}


def verify_fixture(
    policy: AvailabilityPolicy,
    calendar: TradingCalendar,
    fixture_path: str | Path,
) -> list[dict[str, Any]]:
    with Path(fixture_path).open(encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)
    failures: list[dict[str, Any]] = []
    for case in fixture["cases"]:
        result = policy.classify(case["input"], calendar)
        observed = {
            "information_available_at": result["gold"]["information_available_at"],
            "availability_method": result["gold"]["availability_method"],
            "availability_confidence": result["gold"]["availability_confidence"],
            "eligible_session": result["research"]["eligible_session"],
            "eligible_at_open": result["research"]["eligible_at_open"],
            "eligible_at_close": result["research"]["eligible_at_close"],
        }
        if observed != case["expected"]:
            failures.append(
                {
                    "id": case.get("id", "<missing-id>"),
                    "expected": case["expected"],
                    "observed": observed,
                }
            )
    return failures


def _local(session_date: date, hhmm: str, tz: ZoneInfo) -> datetime:
    return datetime.combine(session_date, time.fromisoformat(hhmm), tzinfo=tz)


def _aware_optional(record: Mapping[str, Any], field: str) -> datetime | None:
    value = record.get(field)
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AvailabilityRecordError(f"{field} must include a UTC offset")
    return parsed


def _aware_required(record: Mapping[str, Any], field: str) -> datetime:
    parsed = _aware_optional(record, field)
    if parsed is None:
        raise AvailabilityRecordError(f"{field} is required")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("classify", "verify-fixture"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--config", required=True, type=Path)
        sub.add_argument("--calendar", required=True, type=Path)
        if name == "classify":
            sub.add_argument("--input", required=True, type=Path)
        else:
            sub.add_argument("--fixture", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    policy = AvailabilityPolicy.from_file(args.config)
    calendar = TradingCalendar.from_file(args.calendar)
    if args.command == "classify":
        with args.input.open(encoding="utf-8") as input_file:
            record = json.load(input_file)
        print(json.dumps(policy.classify(record, calendar), indent=2, sort_keys=True))
        return 0
    failures = verify_fixture(policy, calendar, args.fixture)
    if failures:
        print(json.dumps({"status": "failed", "failures": failures}, indent=2))
        return 1
    print(json.dumps({"status": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
