"""Custom OEM plugin scaffold (reference — not loaded by the runtime).

Copy the hooks into ``plugin.py`` when your OEM does not use ``cloud_bench_runner``.
The platform wraps ``execute`` to catch catastrophic failures and maps them to
``plugin_execute_failed`` in ``evaluate``.
"""

from __future__ import annotations

from bmt_sdk import ScoreCaseSummary, averaged_result, custom_plugin, fail_verdict, pass_verdict
from bmt_sdk.context import ExecutionContext
from bmt_sdk.results import ExecutionResult, PreparedAssets, ScoreResult, VerdictResult

SCORE_FIELD = "score"
scoring = averaged_result(SCORE_FIELD)


def prepare(context: ExecutionContext) -> PreparedAssets:
    context.ensure_output_dirs()
    return context.prepared_assets()


def execute(context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
    del context
    del prepared_assets
    # Run your pipeline; raise on unrecoverable errors — the platform wraps execute.
    return ExecutionResult(execution_mode_used="custom", case_results=[])


def score(
    execution_result: ExecutionResult,
    baseline: ScoreResult | None,
    context: ExecutionContext,
) -> ScoreResult:
    del baseline
    summary = ScoreCaseSummary.from_case_results(execution_result.case_results, scoring)
    aggregate = scoring.aggregate_mean_ok_cases(execution_result.case_results)
    metrics = summary.as_metrics()
    metrics[SCORE_FIELD] = aggregate
    return ScoreResult(
        aggregate_score=aggregate,
        metrics=metrics,
        extra={"scoring_policy": scoring.scoring_policy_record(context.plugin_config)},
    )


def evaluate(
    score_result: ScoreResult,
    baseline: ScoreResult | None,
    context: ExecutionContext,
) -> VerdictResult:
    del baseline, context
    if int(score_result.metrics.get("cases_failed", 0) or 0) > 0:
        return fail_verdict("case_failures", summary={"aggregate_score": score_result.aggregate_score})
    return pass_verdict("bootstrap_without_baseline", summary={"aggregate_score": score_result.aggregate_score})


def plugin():
    return custom_plugin(
        project="template-custom",
        scoring=scoring,
        prepare=prepare,
        execute=execute,
        score=score,
        evaluate=evaluate,
    )
