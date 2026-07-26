"""Versioned canonical metric dictionary loading and validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRIC_KINDS = frozenset({"reported", "derived"})
STATEMENTS = frozenset(
    {
        "cover_page",
        "balance_sheet",
        "income_statement",
        "comprehensive_income_statement",
        "cash_flow_statement",
        "shareholders_equity_statement",
        "non_gaap_disclosure",
        "derived",
    }
)
PERIOD_TYPES = frozenset({"instant", "duration"})
UNITS = frozenset({"monetary", "shares", "monetary_per_share", "ratio"})
POLARITIES = frozenset({"debit", "credit", "mixed", "not_applicable"})
DIMENSIONAL_SCOPES = frozenset(
    {"consolidated", "consolidated_or_total", "per_security"}
)
INDUSTRIES = frozenset({"all_release_1"})
MATERIALITY_TIERS = frozenset({"core", "standard", "supplemental"})
FORMULA_METHODS = frozenset({"direct", "calculation", "rolling", "growth", "ratio"})

ROOT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "dictionary_id",
        "dictionary_version",
        "release",
        "status",
        "value_convention",
        "metrics",
    }
)
ROOT_ALLOWED_FIELDS = ROOT_REQUIRED_FIELDS | {"$schema", "description"}
METRIC_REQUIRED_FIELDS = frozenset(
    {
        "metric_id",
        "name",
        "metric_kind",
        "definition",
        "statement",
        "period_type",
        "unit",
        "polarity",
        "dimensional_scope",
        "industry_applicability",
        "industry_exclusions",
        "materiality_tier",
        "formula",
        "fallback_rules",
        "version_added",
    }
)
FORMULA_REQUIRED_FIELDS = frozenset(
    {
        "formula_version",
        "method",
        "expression",
        "required_inputs",
        "optional_inputs",
        "constraints",
    }
)
SNAKE_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class DictionaryValidationError(ValueError):
    """Raised when one or more dictionary-contract checks fail."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    name: str
    metric_kind: str
    definition: str
    statement: str
    period_type: str
    unit: str
    polarity: str
    dimensional_scope: str
    industry_applicability: tuple[str, ...]
    industry_exclusions: tuple[str, ...]
    materiality_tier: str
    formula: Mapping[str, Any] | None
    fallback_rules: tuple[str, ...]
    version_added: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> MetricDefinition:
        formula = payload["formula"]
        return cls(
            metric_id=payload["metric_id"],
            name=payload["name"],
            metric_kind=payload["metric_kind"],
            definition=payload["definition"],
            statement=payload["statement"],
            period_type=payload["period_type"],
            unit=payload["unit"],
            polarity=payload["polarity"],
            dimensional_scope=payload["dimensional_scope"],
            industry_applicability=tuple(payload["industry_applicability"]),
            industry_exclusions=tuple(payload["industry_exclusions"]),
            materiality_tier=payload["materiality_tier"],
            formula=dict(formula) if formula is not None else None,
            fallback_rules=tuple(payload["fallback_rules"]),
            version_added=payload["version_added"],
        )


@dataclass(frozen=True)
class CanonicalDataDictionary:
    schema_version: int
    dictionary_id: str
    dictionary_version: str
    release: str
    value_convention: str
    metrics: tuple[MetricDefinition, ...]
    logical_hash: str

    @classmethod
    def from_file(cls, path: str | Path) -> CanonicalDataDictionary:
        with Path(path).open(encoding="utf-8") as dictionary_file:
            payload = json.load(dictionary_file)
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CanonicalDataDictionary:
        errors = validate_dictionary_payload(payload)
        if errors:
            raise DictionaryValidationError(errors)

        metrics = tuple(
            MetricDefinition.from_mapping(metric) for metric in payload["metrics"]
        )
        canonical_json = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return cls(
            schema_version=payload["schema_version"],
            dictionary_id=payload["dictionary_id"],
            dictionary_version=payload["dictionary_version"],
            release=payload["release"],
            value_convention=payload["value_convention"],
            metrics=metrics,
            logical_hash=hashlib.sha256(canonical_json).hexdigest(),
        )

    @property
    def by_id(self) -> dict[str, MetricDefinition]:
        return {metric.metric_id: metric for metric in self.metrics}

    def get(self, metric_id: str) -> MetricDefinition:
        try:
            return self.by_id[metric_id]
        except KeyError as error:
            raise KeyError(f"unknown metric_id {metric_id!r}") from error


def validate_dictionary_payload(payload: Any) -> list[str]:
    """Return all deterministic contract violations in stable order."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["dictionary root must be an object"]

    missing_root = sorted(ROOT_REQUIRED_FIELDS.difference(payload))
    if missing_root:
        errors.append(
            f"dictionary is missing required fields: {', '.join(missing_root)}"
        )
    extra_root = sorted(set(payload).difference(ROOT_ALLOWED_FIELDS))
    if extra_root:
        errors.append(f"dictionary has unknown fields: {', '.join(extra_root)}")

    if payload.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    _validate_nonempty_string(payload, "dictionary_id", "dictionary", errors)
    _validate_semver(payload, "dictionary_version", "dictionary", errors)
    if payload.get("release") != "1":
        errors.append("release must equal '1'")
    if payload.get("status") != "frozen":
        errors.append("status must equal 'frozen'")
    if payload.get("value_convention") != "reported_value_preserved":
        errors.append("value_convention must equal 'reported_value_preserved'")

    metrics = payload.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("metrics must be a non-empty array")
        return errors

    metric_ids: list[str] = []
    formula_inputs: dict[str, tuple[str, ...]] = {}
    for index, metric in enumerate(metrics):
        path = f"metrics[{index}]"
        if not isinstance(metric, dict):
            errors.append(f"{path} must be an object")
            continue

        missing = sorted(METRIC_REQUIRED_FIELDS.difference(metric))
        if missing:
            errors.append(f"{path} is missing required fields: {', '.join(missing)}")
        extra = sorted(set(metric).difference(METRIC_REQUIRED_FIELDS))
        if extra:
            errors.append(f"{path} has unknown fields: {', '.join(extra)}")

        metric_id = metric.get("metric_id")
        if not isinstance(metric_id, str) or not SNAKE_CASE_PATTERN.fullmatch(
            metric_id
        ):
            errors.append(f"{path}.metric_id must be lower snake_case")
            metric_id = f"<invalid:{index}>"
        metric_ids.append(metric_id)

        _validate_nonempty_string(metric, "name", path, errors)
        _validate_nonempty_string(metric, "definition", path, errors)
        _validate_enum(metric, "metric_kind", METRIC_KINDS, path, errors)
        _validate_enum(metric, "statement", STATEMENTS, path, errors)
        _validate_enum(metric, "period_type", PERIOD_TYPES, path, errors)
        _validate_enum(metric, "unit", UNITS, path, errors)
        _validate_enum(metric, "polarity", POLARITIES, path, errors)
        _validate_enum(metric, "dimensional_scope", DIMENSIONAL_SCOPES, path, errors)
        _validate_enum(metric, "materiality_tier", MATERIALITY_TIERS, path, errors)
        _validate_string_array(
            metric,
            "industry_applicability",
            path,
            errors,
            allowed=INDUSTRIES,
            allow_empty=False,
        )
        _validate_string_array(
            metric,
            "industry_exclusions",
            path,
            errors,
            allow_empty=True,
        )
        _validate_string_array(
            metric, "fallback_rules", path, errors, allow_empty=False
        )
        _validate_semver(metric, "version_added", path, errors)

        formula = metric.get("formula")
        metric_kind = metric.get("metric_kind")
        if metric_kind == "derived" and not isinstance(formula, dict):
            errors.append(f"{path}.formula must be an object for derived metrics")
        elif formula is not None and not isinstance(formula, dict):
            errors.append(f"{path}.formula must be an object or null")
        if isinstance(formula, dict):
            required_inputs = _validate_formula(formula, path, errors)
            formula_inputs[metric_id] = required_inputs
            if metric_kind == "derived" and formula.get("method") == "direct":
                errors.append(f"{path}.formula.method cannot be direct when derived")
            if metric_kind == "reported" and formula.get("method") != "direct":
                errors.append(f"{path}.formula.method must be direct when reported")
        if metric_kind == "derived" and metric.get("statement") != "derived":
            errors.append(
                f"{path}.statement must be derived when metric_kind is derived"
            )
        if metric_kind == "reported" and metric.get("statement") == "derived":
            errors.append(
                f"{path}.statement cannot be derived when metric_kind is reported"
            )

    duplicates = sorted(
        metric_id for metric_id in set(metric_ids) if metric_ids.count(metric_id) > 1
    )
    if duplicates:
        errors.append(f"duplicate metric IDs: {', '.join(duplicates)}")

    known_ids = set(metric_ids)
    for metric_id, inputs in formula_inputs.items():
        for input_id in inputs:
            if input_id == metric_id:
                errors.append(f"{metric_id}.formula cannot depend on itself")
            elif input_id not in known_ids:
                errors.append(
                    f"{metric_id}.formula references unknown metric {input_id}"
                )

    errors.extend(_find_formula_cycles(formula_inputs, known_ids))
    return errors


def _validate_formula(
    formula: Mapping[str, Any], metric_path: str, errors: list[str]
) -> tuple[str, ...]:
    path = f"{metric_path}.formula"
    missing = sorted(FORMULA_REQUIRED_FIELDS.difference(formula))
    if missing:
        errors.append(f"{path} is missing required fields: {', '.join(missing)}")
    extra = sorted(set(formula).difference(FORMULA_REQUIRED_FIELDS))
    if extra:
        errors.append(f"{path} has unknown fields: {', '.join(extra)}")

    _validate_semver(formula, "formula_version", path, errors)
    _validate_enum(formula, "method", FORMULA_METHODS, path, errors)
    _validate_nonempty_string(formula, "expression", path, errors)
    required = _validate_string_array(
        formula,
        "required_inputs",
        path,
        errors,
        allow_empty=True,
        require_metric_ids=True,
    )
    optional = _validate_string_array(
        formula,
        "optional_inputs",
        path,
        errors,
        allow_empty=True,
        require_metric_ids=True,
    )
    _validate_string_array(formula, "constraints", path, errors, allow_empty=False)
    overlap = sorted(set(required).intersection(optional))
    if overlap:
        errors.append(
            f"{path} repeats inputs as required and optional: {', '.join(overlap)}"
        )
    return tuple(required) + tuple(optional)


def _validate_nonempty_string(
    payload: Mapping[str, Any], field: str, path: str, errors: list[str]
) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{field} must be a non-empty string")


def _validate_semver(
    payload: Mapping[str, Any], field: str, path: str, errors: list[str]
) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not SEMVER_PATTERN.fullmatch(value):
        errors.append(f"{path}.{field} must be semantic version X.Y.Z")


def _validate_enum(
    payload: Mapping[str, Any],
    field: str,
    allowed: frozenset[str],
    path: str,
    errors: list[str],
) -> None:
    value = payload.get(field)
    if value not in allowed:
        errors.append(f"{path}.{field} must be one of: {', '.join(sorted(allowed))}")


def _validate_string_array(
    payload: Mapping[str, Any],
    field: str,
    path: str,
    errors: list[str],
    *,
    allow_empty: bool,
    allowed: frozenset[str] | None = None,
    require_metric_ids: bool = False,
) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list):
        errors.append(f"{path}.{field} must be an array")
        return ()
    if not value and not allow_empty:
        errors.append(f"{path}.{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path}.{field} must contain only non-empty strings")
        return ()
    if len(value) != len(set(value)):
        errors.append(f"{path}.{field} must not contain duplicates")
    invalid = sorted(item for item in value if allowed and item not in allowed)
    if invalid:
        errors.append(f"{path}.{field} contains invalid values: {', '.join(invalid)}")
    if require_metric_ids:
        invalid_ids = sorted(
            item for item in value if not SNAKE_CASE_PATTERN.fullmatch(item)
        )
        if invalid_ids:
            errors.append(
                f"{path}.{field} contains invalid metric IDs: {', '.join(invalid_ids)}"
            )
    return tuple(value)


def _find_formula_cycles(
    formula_inputs: Mapping[str, tuple[str, ...]], known_ids: set[str]
) -> list[str]:
    graph = {
        metric_id: tuple(input_id for input_id in inputs if input_id in formula_inputs)
        for metric_id, inputs in formula_inputs.items()
        if metric_id in known_ids
    }
    state: dict[str, int] = {}
    stack: list[str] = []
    errors: list[str] = []

    def visit(metric_id: str) -> None:
        state[metric_id] = 1
        stack.append(metric_id)
        for dependency in graph.get(metric_id, ()):
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                cycle = stack[start:] + [dependency]
                message = f"formula dependency cycle: {' -> '.join(cycle)}"
                if message not in errors:
                    errors.append(message)
        stack.pop()
        state[metric_id] = 2

    for metric_id in sorted(graph):
        if state.get(metric_id, 0) == 0:
            visit(metric_id)
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--dictionary", required=True, type=Path)

    show = subparsers.add_parser("show")
    show.add_argument("--dictionary", required=True, type=Path)
    show.add_argument("--metric", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        dictionary = CanonicalDataDictionary.from_file(args.dictionary)
    except (DictionaryValidationError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "invalid", "errors": str(error).splitlines()},
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    if args.command == "show":
        try:
            metric = dictionary.get(args.metric)
        except KeyError as error:
            print(json.dumps({"status": "not_found", "error": str(error)}))
            return 1
        print(
            json.dumps(
                {
                    field: getattr(metric, field)
                    for field in metric.__dataclass_fields__
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(
        json.dumps(
            {
                "dictionary_id": dictionary.dictionary_id,
                "dictionary_version": dictionary.dictionary_version,
                "logical_hash": dictionary.logical_hash,
                "metric_count": len(dictionary.metrics),
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
