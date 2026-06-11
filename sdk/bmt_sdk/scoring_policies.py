"""Worker-neutral scoring helper utilities used by plugin policies."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from bmt_sdk.results import CaseResult

Comparison = Literal["gte", "lte"]


def normalize_comparison(plugin_config: dict[str, Any]) -> Comparison:
    raw = str(plugin_config.get("comparison", "gte")).strip().lower()
    return "lte" if raw == "lte" else "gte"


def score_direction_hint(comparison: Comparison) -> str:
    return "lower_better" if comparison == "lte" else "higher_better"


def score_direction_label(comparison: Comparison) -> str:
    return "lower better" if comparison == "lte" else "higher better"


def scoring_policy_record(
    *,
    plugin_config: dict[str, Any],
    schema_version: str = "3",
    reducer: str = "mean_ok_cases",
    failure_policy: str = "ignore_case_failures",
) -> dict[str, Any]:
    """Build a stable ``ScoreResult.extra['scoring_policy']`` payload."""

    comparison = normalize_comparison(plugin_config)
    tolerance = float(plugin_config.get("tolerance_abs", 0.25) or 0.25)
    normalized_reducer = str(plugin_config.get("aggregation", reducer) or reducer).strip()
    if normalized_reducer != "mean_ok_cases":
        normalized_reducer = "mean_ok_cases"
    out: dict[str, Any] = {
        "schema_version": schema_version,
        "reducer": normalized_reducer,
        "failure_policy": failure_policy,
        "comparison": comparison,
        "tolerance_abs": tolerance,
        "score_direction_hint": score_direction_hint(comparison),
        "score_direction_label": score_direction_label(comparison),
    }
    keyword = plugin_config.get("keyword")
    if isinstance(keyword, str) and keyword.strip():
        out["keyword"] = keyword.strip()
    hints = plugin_config.get("reporting_hints")
    if isinstance(hints, dict):
        out["reporting_hints"] = {str(k): v for k, v in hints.items()}
    return out


def aggregate_mean_ok_cases(case_results: list[CaseResult], *, field: str) -> float:
    ok = [row for row in case_results if row.status == "ok"]
    if not ok:
        return 0.0
    values = [float(row.metrics.get(field, 0.0)) for row in ok]
    return sum(values) / len(values)


def build_case_outcomes(
    case_results: list[CaseResult],
    *,
    field: str,
    max_error_chars: int = 2000,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for result in case_results:
        error_text = (result.error or "").strip()
        if len(error_text) > max_error_chars:
            error_text = error_text[: max_error_chars - 3] + "..."
        log_name = ""
        log_path = result.artifacts.get("log_path")
        if isinstance(log_path, str) and log_path.strip():
            log_name = Path(log_path).name
        outcomes.append(
            {
                "case_id": result.case_id,
                "status": result.status,
                field: float(result.metrics.get(field, 0.0)),
                "error": error_text,
                "log_name": log_name,
            }
        )
    return outcomes
