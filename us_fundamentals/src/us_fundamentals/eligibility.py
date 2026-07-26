"""Executable Release 1 filing-eligibility policy.

The policy consumes normalized filing metadata. Source-specific classification
of registrant and issuer types belongs in acquisition code; this module is the
single authority for deciding whether that normalized record is in Release 1.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class PolicyConfigurationError(ValueError):
    """Raised when a policy file violates the executable contract."""


class FilingRecordError(ValueError):
    """Raised when non-eligibility metadata uses an unknown value."""


@dataclass(frozen=True)
class EligibilityDecision:
    """A policy result kept separate from ingestion state."""

    accession: str | None
    policy_id: str
    policy_version: str
    eligibility_status: str
    reason_codes: tuple[str, ...]
    ingestion_status: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "eligibility_status": self.eligibility_status,
            "reason_codes": list(self.reason_codes),
            "ingestion_status": self.ingestion_status,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ReleasePolicy:
    """Validated policy values used by ingestion and inventory jobs."""

    policy_id: str
    policy_version: str
    filing_start: datetime
    required_fields: tuple[str, ...]
    supported_forms: frozenset[str]
    included_accounting_standards: frozenset[str]
    unsupported_accounting_standards: frozenset[str]
    included_registrant_types: frozenset[str]
    unsupported_registrant_types: frozenset[str]
    indeterminate_registrant_type: str
    included_issuer_types: frozenset[str]
    unsupported_issuer_types: frozenset[str]
    indeterminate_issuer_type: str
    ingestion_statuses: frozenset[str]
    default_ingestion_status: str
    metric_later_start_allowed: bool
    metric_later_start_requires_evidence: bool
    metric_later_start_requires_version_increment: bool

    @classmethod
    def from_file(cls, path: str | Path) -> ReleasePolicy:
        with Path(path).open(encoding="utf-8") as policy_file:
            payload = json.load(policy_file)
        if not isinstance(payload, dict):
            raise PolicyConfigurationError("policy root must be an object")
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ReleasePolicy:
        required_sections = {
            "policy_id",
            "policy_version",
            "status",
            "filing_start",
            "required_eligibility_fields",
            "supported_forms",
            "accounting_standards",
            "registrant_types",
            "issuer_types",
            "ingestion",
            "release_scope",
            "metric_supported_start_policy",
        }
        missing_sections = sorted(required_sections.difference(payload))
        if missing_sections:
            raise PolicyConfigurationError(
                f"policy is missing sections: {', '.join(missing_sections)}"
            )
        if payload["status"] != "frozen":
            raise PolicyConfigurationError("Release 1 policy status must be frozen")

        filing_start = _mapping(payload, "filing_start")
        if (
            filing_start.get("field") != "sec_acceptance_datetime"
            or filing_start.get("operator") != "on_or_after"
        ):
            raise PolicyConfigurationError(
                "filing_start must use sec_acceptance_datetime with on_or_after"
            )
        filing_start_value = _aware_datetime(
            filing_start.get("value"), "filing_start.value", PolicyConfigurationError
        )

        accounting_standards = _mapping(payload, "accounting_standards")
        registrant_types = _mapping(payload, "registrant_types")
        issuer_types = _mapping(payload, "issuer_types")
        ingestion = _mapping(payload, "ingestion")
        metric_start = _mapping(payload, "metric_supported_start_policy")

        if ingestion.get("eligibility_is_independent") is not True:
            raise PolicyConfigurationError(
                "ingestion.eligibility_is_independent must be true"
            )
        if metric_start.get("later_start_allowed") is not True:
            raise PolicyConfigurationError(
                "metric_supported_start_policy must permit evidence-backed later starts"
            )

        policy = cls(
            policy_id=_nonempty_string(payload.get("policy_id"), "policy_id"),
            policy_version=_nonempty_string(
                payload.get("policy_version"), "policy_version"
            ),
            filing_start=filing_start_value,
            required_fields=_string_tuple(
                payload.get("required_eligibility_fields"),
                "required_eligibility_fields",
            ),
            supported_forms=frozenset(
                _string_tuple(payload.get("supported_forms"), "supported_forms")
            ),
            included_accounting_standards=frozenset(
                _string_tuple(
                    accounting_standards.get("included"),
                    "accounting_standards.included",
                )
            ),
            unsupported_accounting_standards=frozenset(
                _string_tuple(
                    accounting_standards.get("recognized_unsupported"),
                    "accounting_standards.recognized_unsupported",
                )
            ),
            included_registrant_types=frozenset(
                _string_tuple(
                    registrant_types.get("included"), "registrant_types.included"
                )
            ),
            unsupported_registrant_types=frozenset(
                _string_tuple(
                    registrant_types.get("recognized_unsupported"),
                    "registrant_types.recognized_unsupported",
                )
            ),
            indeterminate_registrant_type=_nonempty_string(
                registrant_types.get("indeterminate"),
                "registrant_types.indeterminate",
            ),
            included_issuer_types=frozenset(
                _string_tuple(issuer_types.get("included"), "issuer_types.included")
            ),
            unsupported_issuer_types=frozenset(
                _string_tuple(
                    issuer_types.get("recognized_unsupported"),
                    "issuer_types.recognized_unsupported",
                )
            ),
            indeterminate_issuer_type=_nonempty_string(
                issuer_types.get("indeterminate"), "issuer_types.indeterminate"
            ),
            ingestion_statuses=frozenset(
                _string_tuple(ingestion.get("statuses"), "ingestion.statuses")
            ),
            default_ingestion_status=_nonempty_string(
                ingestion.get("default_status"), "ingestion.default_status"
            ),
            metric_later_start_allowed=True,
            metric_later_start_requires_evidence=_required_true(
                metric_start,
                "requires_empirical_quality_evidence",
                "metric_supported_start_policy",
            ),
            metric_later_start_requires_version_increment=_required_true(
                metric_start,
                "requires_policy_version_increment",
                "metric_supported_start_policy",
            ),
        )
        policy._validate_sets()
        return policy

    def _validate_sets(self) -> None:
        classifications = (
            (
                "accounting_standards",
                self.included_accounting_standards,
                self.unsupported_accounting_standards,
            ),
            (
                "registrant_types",
                self.included_registrant_types,
                self.unsupported_registrant_types,
            ),
            (
                "issuer_types",
                self.included_issuer_types,
                self.unsupported_issuer_types,
            ),
        )
        for name, included, unsupported in classifications:
            overlap = sorted(included.intersection(unsupported))
            if overlap:
                raise PolicyConfigurationError(
                    f"{name} includes and excludes the same values: {overlap}"
                )
        if self.default_ingestion_status not in self.ingestion_statuses:
            raise PolicyConfigurationError(
                "ingestion.default_status must occur in ingestion.statuses"
            )

    def evaluate(self, record: Mapping[str, Any]) -> EligibilityDecision:
        """Classify one normalized filing without conflating acquisition state."""

        ingestion_status = record.get("ingestion_status", self.default_ingestion_status)
        if ingestion_status not in self.ingestion_statuses:
            raise FilingRecordError(
                f"unknown ingestion_status {ingestion_status!r}; "
                f"expected one of {sorted(self.ingestion_statuses)}"
            )

        missing_fields = [
            field for field in self.required_fields if _is_missing(record.get(field))
        ]
        invalid_fields: dict[str, str] = {}
        exclusion_reasons: list[str] = []
        indeterminate_reasons: list[str] = []

        form = _optional_string(record.get("form"))
        if form is not None and form not in self.supported_forms:
            exclusion_reasons.append("unsupported_form")

        standard = _optional_string(record.get("accounting_standard"))
        if standard is not None:
            if standard in self.unsupported_accounting_standards:
                exclusion_reasons.append("unsupported_accounting_standard")
            elif standard not in self.included_accounting_standards:
                indeterminate_reasons.append("unknown_accounting_standard")

        registrant_type = _optional_string(record.get("registrant_type"))
        if registrant_type is not None:
            if registrant_type in self.unsupported_registrant_types:
                exclusion_reasons.append("unsupported_registrant_type")
            elif registrant_type not in self.included_registrant_types:
                indeterminate_reasons.append("unknown_registrant_type")

        issuer_type = _optional_string(record.get("issuer_type"))
        if issuer_type is not None:
            if issuer_type in self.unsupported_issuer_types:
                exclusion_reasons.append("unsupported_issuer_type")
            elif issuer_type not in self.included_issuer_types:
                indeterminate_reasons.append("unknown_issuer_type")

        acceptance_value = record.get("sec_acceptance_datetime")
        acceptance_datetime: datetime | None = None
        if not _is_missing(acceptance_value):
            try:
                acceptance_datetime = _aware_datetime(
                    acceptance_value,
                    "sec_acceptance_datetime",
                    FilingRecordError,
                )
            except FilingRecordError as error:
                invalid_fields["sec_acceptance_datetime"] = str(error)
                indeterminate_reasons.append("invalid_sec_acceptance_datetime")
        if acceptance_datetime is not None and acceptance_datetime < self.filing_start:
            exclusion_reasons.append("before_release_start")

        if exclusion_reasons:
            status = "excluded"
            reasons = tuple(dict.fromkeys(exclusion_reasons))
        else:
            if missing_fields:
                indeterminate_reasons.insert(0, "missing_required_field")
            if indeterminate_reasons:
                status = "indeterminate"
                reasons = tuple(dict.fromkeys(indeterminate_reasons))
            else:
                status = "eligible"
                reasons = ("eligible",)

        details: dict[str, Any] = {}
        if missing_fields:
            details["missing_fields"] = missing_fields
        if invalid_fields:
            details["invalid_fields"] = invalid_fields

        return EligibilityDecision(
            accession=_optional_string(record.get("accession")),
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            eligibility_status=status,
            reason_codes=reasons,
            ingestion_status=str(ingestion_status),
            details=details,
        )


def verify_fixture(
    policy: ReleasePolicy, fixture_path: str | Path
) -> list[dict[str, Any]]:
    with Path(fixture_path).open(encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)
    cases = fixture.get("cases") if isinstance(fixture, dict) else None
    if not isinstance(cases, list):
        raise FilingRecordError("fixture root must contain a cases array")

    failures: list[dict[str, Any]] = []
    for case in cases:
        case_id = case.get("id", "<missing-id>")
        decision = policy.evaluate(case.get("input", {})).to_dict()
        expected = case.get("expected", {})
        observed = {
            "eligibility_status": decision["eligibility_status"],
            "reason_codes": decision["reason_codes"],
            "ingestion_status": decision["ingestion_status"],
        }
        if observed != expected:
            failures.append({"id": case_id, "expected": expected, "observed": observed})
    return failures


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise PolicyConfigurationError(f"{key} must be an object")
    return value


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyConfigurationError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise PolicyConfigurationError(
            f"{field} must be a non-empty array of non-empty strings"
        )
    if len(value) != len(set(value)):
        raise PolicyConfigurationError(f"{field} must not contain duplicates")
    return tuple(value)


def _required_true(payload: Mapping[str, Any], key: str, section: str) -> bool:
    if payload.get(key) is not True:
        raise PolicyConfigurationError(f"{section}.{key} must be true")
    return True


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _aware_datetime(value: Any, field: str, error_type: type[ValueError]) -> datetime:
    if not isinstance(value, str):
        raise error_type(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise error_type(f"{field} must be a valid ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise error_type(f"{field} must include a UTC offset")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-policy")
    validate.add_argument("--config", required=True, type=Path)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--config", required=True, type=Path)
    classify.add_argument("--input", required=True, type=Path)

    fixture = subparsers.add_parser("verify-fixture")
    fixture.add_argument("--config", required=True, type=Path)
    fixture.add_argument("--fixture", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    policy = ReleasePolicy.from_file(args.config)

    if args.command == "validate-policy":
        print(
            json.dumps(
                {
                    "policy_id": policy.policy_id,
                    "policy_version": policy.policy_version,
                    "status": "valid",
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "classify":
        with args.input.open(encoding="utf-8") as input_file:
            record = json.load(input_file)
        print(json.dumps(policy.evaluate(record).to_dict(), indent=2, sort_keys=True))
        return 0

    failures = verify_fixture(policy, args.fixture)
    if failures:
        print(json.dumps({"status": "failed", "failures": failures}, indent=2))
        return 1
    print(json.dumps({"status": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
