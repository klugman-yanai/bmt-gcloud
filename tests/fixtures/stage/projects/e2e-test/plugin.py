from __future__ import annotations

from bmt_sdk import custom_plugin, custom_scoring
from bmt_sdk.context import ExecutionContext
from bmt_sdk.results import CaseResult, ExecutionResult, PreparedAssets, ScoreResult, VerdictResult

from runtime.config.bmt_domain_status import BmtLegStatus

e2e_scoring = custom_scoring(
    aggregate=lambda cases: float(cases[0].metrics.get("lines_read", 0.0)) if cases else 0.0,
    build_outcomes=lambda cases: [{"case_id": c.case_id, "status": c.status} for c in cases],
    policy_record=lambda _cfg: {
        "comparison": "gte",
        "score_direction_hint": "higher_better",
        "score_direction_label": "higher better",
    },
)


def prepare(context: ExecutionContext) -> PreparedAssets:
    if not context.dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {context.dataset_root}")
    input_file = context.dataset_root / "test_input.txt"
    if not input_file.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    return PreparedAssets(
        dataset_root=context.dataset_root,
        workspace_root=context.workspace_root,
    )


def execute(context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
    del prepared_assets
    input_file = context.dataset_root / "test_input.txt"
    with input_file.open(encoding="utf-8") as handle:
        lines_read = len(handle.readlines())
    return ExecutionResult(
        execution_mode_used="e2e-test",
        case_results=[
            CaseResult(
                case_id="test_input.txt",
                input_path=input_file,
                exit_code=0,
                status="ok",
                metrics={"lines_read": float(lines_read)},
                artifacts={},
                error="",
            )
        ],
        raw_summary={"status": "success", "lines_read": lines_read},
    )


def score(
    execution_result: ExecutionResult,
    baseline: ScoreResult | None,
    context: ExecutionContext,
) -> ScoreResult:
    del baseline, context
    lines = float(execution_result.case_results[0].metrics.get("lines_read", 0.0))
    return ScoreResult(aggregate_score=lines, metrics={"lines_read": lines})


def evaluate(
    score_result: ScoreResult,
    baseline: ScoreResult | None,
    context: ExecutionContext,
) -> VerdictResult:
    del baseline, context
    return VerdictResult(
        passed=True,
        status=BmtLegStatus.PASS.value,
        reason_code="e2e_test_passed",
        summary={"detail": "E2E test passed successfully."},
    )


def plugin():
    return custom_plugin(
        project="e2e-test",
        scoring=e2e_scoring,
        prepare=prepare,
        execute=execute,
        score=score,
        evaluate=evaluate,
    )
