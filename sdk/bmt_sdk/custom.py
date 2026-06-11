"""Factory for custom (non-runner) BMT plugins."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from bmt_sdk.context import ExecutionContext
from bmt_sdk.cloud_task_spec import CloudTaskSpec
from bmt_sdk.scoring import ScoringPolicy
from bmt_sdk.plugin import BmtPlugin
from bmt_sdk.results import CaseResult, ExecutionResult, PreparedAssets, ScoreResult, VerdictResult, fail_verdict

logger = logging.getLogger(__name__)

PrepareHook = Callable[[ExecutionContext], PreparedAssets]
ExecuteHook = Callable[[ExecutionContext, PreparedAssets], ExecutionResult]
ScoreHook = Callable[[ExecutionResult, ScoreResult | None, ExecutionContext], ScoreResult]
EvaluateHook = Callable[[ScoreResult, ScoreResult | None, ExecutionContext], VerdictResult]


def _effective_execute_exception_key(project: str, override: str | None) -> str:
    return override or f"{project}_plugin_execute_exception"


@dataclass
class _CustomPluginImpl:
    plugin_name: str
    scoring: ScoringPolicy
    cloud_task: CloudTaskSpec = field(default_factory=CloudTaskSpec)
    api_version: str = "v1"
    execute_exception_key: str | None = None
    _prepare: PrepareHook | None = None
    _execute: ExecuteHook | None = None
    _score: ScoreHook | None = None
    _evaluate: EvaluateHook | None = None

    @property
    def scoring_policy(self) -> ScoringPolicy:
        return self.scoring

    @property
    def effective_execute_exception_key(self) -> str:
        return _effective_execute_exception_key(self.plugin_name, self.execute_exception_key)

    def prepare(self, context: ExecutionContext) -> PreparedAssets:
        if self._prepare is not None:
            return self._prepare(context)
        context.ensure_output_dirs()
        return context.prepared_assets()

    def execute(self, context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
        if self._execute is None:
            raise RuntimeError(f"custom_plugin for {self.plugin_name} requires execute=")
        try:
            return self._execute(context, prepared_assets)
        except Exception as exc:
            logger.exception(
                "%s plugin execute failed for bmt=%s",
                self.plugin_name,
                context.bmt_manifest.bmt_slug,
            )
            return ExecutionResult(
                execution_mode_used="custom",
                case_results=[
                    CaseResult(
                        case_id="_execute_",
                        input_path=prepared_assets.dataset_root,
                        exit_code=-1,
                        status="failed",
                        metrics={},
                        artifacts={},
                        error=f"{type(exc).__name__}:{exc}",
                    )
                ],
                raw_summary={self.effective_execute_exception_key: True},
            )

    def score(
        self,
        execution_result: ExecutionResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> ScoreResult:
        if self._score is None:
            raise RuntimeError(f"custom_plugin for {self.plugin_name} requires score=")
        result = self._score(execution_result, baseline, context)
        key = self.effective_execute_exception_key
        if not execution_result.raw_summary.get(key):
            return result
        extra = dict(result.extra)
        extra[key] = True
        return ScoreResult(
            aggregate_score=result.aggregate_score,
            metrics=result.metrics,
            extra=extra,
        )

    def evaluate(
        self,
        score_result: ScoreResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> VerdictResult:
        if self._evaluate is None:
            raise RuntimeError(f"custom_plugin for {self.plugin_name} requires evaluate=")
        key = self.effective_execute_exception_key
        if score_result.extra.get(key):
            return fail_verdict(
                "plugin_execute_failed",
                summary={"aggregate_score": score_result.aggregate_score},
            )
        return self._evaluate(score_result, baseline, context)


def custom_plugin(
    *,
    project: str,
    scoring: ScoringPolicy,
    cloud_task: CloudTaskSpec | None = None,
    prepare: PrepareHook | None = None,
    execute: ExecuteHook | None = None,
    score: ScoreHook | None = None,
    evaluate: EvaluateHook | None = None,
    execute_exception_key: str | None = None,
) -> BmtPlugin:
    """Build a custom BMT plugin from callables without subclassing."""

    return _CustomPluginImpl(
        plugin_name=project,
        scoring=scoring,
        cloud_task=cloud_task or CloudTaskSpec(),
        execute_exception_key=execute_exception_key,
        _prepare=prepare,
        _execute=execute,
        _score=score,
        _evaluate=evaluate,
    )
