"""Typed worker RPC contracts for plugin hook execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bmt_sdk.results import ExecutionResult, ScoreResult, VerdictResult


class WorkerContractModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PluginInvocation(WorkerContractModel):
    project: str = Field(min_length=1)
    plugin_id: str = Field(min_length=1)
    plugin_version: str = Field(min_length=1)


class WorkerContextEnvelope(WorkerContractModel):
    workspace_root: Path
    dataset_root: Path
    outputs_root: Path
    logs_root: Path
    plugin_root: Path
    bmt_slug: str = Field(min_length=1)
    bmt_id: str = Field(min_length=1)
    project_description: str = ""
    execution_policy: str = "adaptive_batch_then_legacy"
    execution_profile: str = "standard"
    runner_template_path: str = "runtime/assets/cloud_bench_input_template.json"
    workflow_run_id: str | None = None
    plugin_config: dict[str, Any] = Field(default_factory=dict)
    runner_path: Path | None = None
    deps_root: Path | None = None


class PrepareRequest(WorkerContractModel):
    plugin: PluginInvocation
    context: WorkerContextEnvelope


class PrepareResponse(WorkerContractModel):
    prepared_assets_extra: dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(WorkerContractModel):
    plugin: PluginInvocation
    context: WorkerContextEnvelope
    prepared_assets_extra: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(WorkerContractModel):
    execution_result: ExecutionResult


class ScoreRequest(WorkerContractModel):
    plugin: PluginInvocation
    context: WorkerContextEnvelope
    execution_result: ExecutionResult
    baseline: ScoreResult | None = None


class ScoreResponse(WorkerContractModel):
    score_result: ScoreResult


class EvaluateRequest(WorkerContractModel):
    plugin: PluginInvocation
    context: WorkerContextEnvelope
    score_result: ScoreResult
    baseline: ScoreResult | None = None


class EvaluateResponse(WorkerContractModel):
    verdict_result: VerdictResult
