"""Contributor plugin contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from bmt_sdk.context import ExecutionContext
from bmt_sdk.cloud_task_spec import CloudTaskSpec
from bmt_sdk.results import ExecutionResult, PreparedAssets, ScoreResult, VerdictResult

__all__ = ["BmtPlugin", "CloudTaskSpec"]


@runtime_checkable
class BmtPlugin(Protocol):
    """Hook contract for Cloud BMT plugins.

    Call order: :meth:`prepare` → :meth:`execute` → :meth:`score` → :meth:`evaluate`.
    """

    plugin_name: str
    api_version: str
    cloud_task: CloudTaskSpec

    def prepare(self, context: ExecutionContext) -> PreparedAssets:
        """Paths and tools before :meth:`execute` (keep it light)."""

    def execute(self, context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
        """One :class:`CaseResult` per input; ``status="failed"`` for runner or parse errors."""

    def score(
        self,
        execution_result: ExecutionResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> ScoreResult:
        """Counters in ``metrics``; policy and check-run copy in ``extra``."""

    def evaluate(
        self,
        score_result: ScoreResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> VerdictResult:
        """Stable machine ``reason_code``; reporting turns that into check text."""
