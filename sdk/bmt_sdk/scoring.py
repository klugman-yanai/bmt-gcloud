"""Scoring policy types and factories for bench plugins."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field

from bmt_sdk import scoring_policies as _scoring_helpers
from bmt_sdk.plugin_models import ScoringPolicyRecord, StrictPluginModel
from bmt_sdk.results import CaseResult

ScoreFieldName = str


class FailurePolicy(StrEnum):
    """How per-case runner failures interact with test score and verdict.

    ``IGNORE_CASE_FAILURES`` (SK default):
        Average the configured score field only over cases the runner marked ``ok``. A few failed WAVs
        do not auto-fail the test; only ``no_successful_cases`` fails. Failures stay in metrics.

    ``FAIL_ON_ANY_CASE_FAILURE``:
        Any failed case fails the test. Enforced by the runner ``evaluate`` hook when set on
        ``custom_plugin(..., scoring=...)`` (via ``custom scoring(failure_policy=...)`` or
        ``averaged_result(..., failure_policy=...)``).
    """

    IGNORE_CASE_FAILURES = "ignore_case_failures"
    FAIL_ON_ANY_CASE_FAILURE = "fail_on_any_case_failure"


class ScoringPolicy(Protocol):
    """Project scoring policy used by runner and custom plugins."""

    def aggregate_mean_ok_cases(self, case_results: list[CaseResult]) -> float: ...

    def build_case_outcomes(self, case_results: list[CaseResult]) -> list[dict[str, object]]: ...

    def scoring_policy_record(self, plugin_config: Mapping[str, object]) -> dict[str, object]: ...


ScoringPolicyProtocol = ScoringPolicy


class ScoreCaseSummary(StrictPluginModel):
    """Typed summary for per-test case aggregation used across score/evaluate."""

    case_count: int = Field(ge=0)
    cases_ok: int = Field(ge=0)
    cases_failed: int = Field(ge=0)
    cases_failed_ids: tuple[str, ...] = ()
    case_outcomes: list[dict[str, object]] = Field(default_factory=list)

    @classmethod
    def from_case_results(cls, case_results: list[CaseResult], scoring_policy: ScoringPolicy) -> ScoreCaseSummary:
        failed_ids = tuple(case.case_id for case in case_results if case.status != "ok")
        return cls(
            case_count=len(case_results),
            cases_ok=len(case_results) - len(failed_ids),
            cases_failed=len(failed_ids),
            cases_failed_ids=failed_ids,
            case_outcomes=scoring_policy.build_case_outcomes(case_results),
        )

    def as_metrics(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "cases_ok": self.cases_ok,
            "cases_failed": self.cases_failed,
            "cases_failed_ids": list(self.cases_failed_ids),
            "case_outcomes": self.case_outcomes,
        }


class _AveragedResultPolicy:
    def __init__(
        self,
        *,
        field: str,
        failure_policy: FailurePolicy = FailurePolicy.IGNORE_CASE_FAILURES,
        max_error_chars: int = 2000,
        schema_version: str = "3",
        reducer: str = "mean_ok_cases",
    ) -> None:
        self._field = field
        self._failure_policy = failure_policy
        self._max_error_chars = max_error_chars
        self._schema_version = schema_version
        self._reducer = reducer

    def aggregate_mean_ok_cases(self, case_results: list[CaseResult]) -> float:
        return _scoring_helpers.aggregate_mean_ok_cases(case_results, field=self._field)

    def build_case_outcomes(self, case_results: list[CaseResult]) -> list[dict[str, object]]:
        return _scoring_helpers.build_case_outcomes(
            case_results,
            field=self._field,
            max_error_chars=self._max_error_chars,
        )

    def scoring_policy_record(self, plugin_config: Mapping[str, object]) -> dict[str, object]:
        return _scoring_helpers.scoring_policy_record(
            plugin_config=dict(plugin_config),
            schema_version=self._schema_version,
            reducer=self._reducer,
            failure_policy=self._failure_policy.value,
        )


class _CustomScoringPolicy:
    def __init__(
        self,
        *,
        aggregate_mean_ok_cases: Callable[[list[CaseResult]], float],
        build_case_outcomes: Callable[[list[CaseResult]], list[dict[str, object]]],
        scoring_policy_record: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._aggregate_mean_ok_cases = aggregate_mean_ok_cases
        self._build_case_outcomes = build_case_outcomes
        self._scoring_policy_record = scoring_policy_record

    def aggregate_mean_ok_cases(self, case_results: list[CaseResult]) -> float:
        return self._aggregate_mean_ok_cases(case_results)

    def build_case_outcomes(self, case_results: list[CaseResult]) -> list[dict[str, object]]:
        return self._build_case_outcomes(case_results)

    def scoring_policy_record(self, plugin_config: Mapping[str, object]) -> dict[str, object]:
        return self._scoring_policy_record(dict(plugin_config))


def averaged_result(
    field: ScoreFieldName,
    *,
    failure_policy: FailurePolicy = FailurePolicy.IGNORE_CASE_FAILURES,
    max_error_chars: int = 2000,
    schema_version: str = "3",
    reducer: str = "mean_ok_cases",
) -> ScoringPolicy:
    """Build a scoring policy that averages one numeric case value."""

    normalized_metric = getattr(field, "value", field)
    return _AveragedResultPolicy(
        field=str(normalized_metric),
        failure_policy=failure_policy,
        max_error_chars=max_error_chars,
        schema_version=schema_version,
        reducer=reducer,
    )


def custom_scoring(
    *,
    aggregate: Callable[[list[CaseResult]], float],
    build_outcomes: Callable[[list[CaseResult]], list[dict[str, object]]],
    policy_record: Callable[[dict[str, Any]], dict[str, Any]],
) -> ScoringPolicy:
    """Adapter for project-specific scoring functions."""

    return _CustomScoringPolicy(
        aggregate_mean_ok_cases=aggregate,
        build_case_outcomes=build_outcomes,
        scoring_policy_record=policy_record,
    )


__all__ = [
    "FailurePolicy",
    "ScoreCaseSummary",
    "ScoringPolicy",
    "ScoringPolicyProtocol",
    "ScoringPolicyRecord",
    "averaged_result",
    "custom_scoring",
]
