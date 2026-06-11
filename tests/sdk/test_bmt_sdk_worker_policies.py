from __future__ import annotations

from pathlib import Path

from bmt_sdk.results import CaseResult
from bmt_sdk.worker import (
    aggregate_mean_ok_cases,
    build_case_outcomes,
    scoring_policy_record,
)


def test_scoring_policy_record_sets_direction_and_hints() -> None:
    payload = scoring_policy_record(
        plugin_config={"comparison": "lte", "tolerance_abs": 0.1, "reporting_hints": {"foo": "bar"}},
    )
    assert payload["comparison"] == "lte"
    assert payload["score_direction_hint"] == "lower_better"
    assert payload["reporting_hints"]["foo"] == "bar"


def test_aggregate_and_case_outcomes_helpers() -> None:
    cases = [
        CaseResult(case_id="a", input_path=Path("a.wav"), exit_code=0, status="ok", metrics={"m": 1.0}),
        CaseResult(case_id="b", input_path=Path("b.wav"), exit_code=0, status="ok", metrics={"m": 3.0}),
        CaseResult(case_id="c", input_path=Path("c.wav"), exit_code=1, status="failed", metrics={"m": 50.0}),
    ]
    assert aggregate_mean_ok_cases(cases, field="m") == 2.0
    outcomes = build_case_outcomes(cases, field="m")
    assert outcomes[0]["m"] == 1.0
    assert outcomes[2]["status"] == "failed"
