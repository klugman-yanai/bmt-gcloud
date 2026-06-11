"""Stable bench plugin SDK for the cloud CI handoff template."""

from bmt_sdk.cloud_task_spec import BenchTest, CloudTaskProfile, CloudTaskSpec, default_cloud_task
from bmt_sdk.context import ExecutionContext
from bmt_sdk.custom import custom_plugin
from bmt_sdk.plugin import BmtPlugin
from bmt_sdk.results import (
    CaseResult,
    ExecutionResult,
    PreparedAssets,
    ScoreResult,
    VerdictResult,
    fail_verdict,
    pass_verdict,
)
from bmt_sdk.scoring import FailurePolicy, ScoreCaseSummary, averaged_result, custom_scoring

__all__ = [
    "BenchTest",
    "BmtPlugin",
    "CaseResult",
    "CloudTaskProfile",
    "CloudTaskSpec",
    "ExecutionContext",
    "ExecutionResult",
    "FailurePolicy",
    "PreparedAssets",
    "ScoreCaseSummary",
    "ScoreResult",
    "VerdictResult",
    "averaged_result",
    "custom_plugin",
    "custom_scoring",
    "default_cloud_task",
    "fail_verdict",
    "pass_verdict",
]
