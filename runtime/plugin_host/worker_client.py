"""Worker client that executes plugin hooks in an isolated worker process boundary."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import cast

from bmt_sdk.context import ExecutionContext
from bmt_sdk.results import ExecutionResult, PreparedAssets, ScoreResult, VerdictResult
from bmt_sdk.worker.contracts import (
    EvaluateRequest,
    ExecuteRequest,
    PluginInvocation,
    PrepareRequest,
    ScoreRequest,
    WorkerContextEnvelope,
)
from bmt_sdk.worker.worker import PluginWorker

from runtime.plugin_host.deps_env import prepare_plugin_dependency_sys_paths
from runtime.plugin_host.worker_protocol import WorkerRuntimeTarget


def _load_worker(project_dir: Path, target: WorkerRuntimeTarget) -> PluginWorker:
    entrypoint = target.entrypoint
    module_path, _, symbol = entrypoint.partition(":")
    if not module_path or not symbol:
        raise ValueError(f"Invalid worker entrypoint {entrypoint!r}; expected 'module.path:ClassName'")
    dep_paths = prepare_plugin_dependency_sys_paths(project_dir, target)
    candidate_paths = [*dep_paths, project_dir]
    plugins_root = project_dir / "plugins"
    if plugins_root.is_dir():
        for src_dir in plugins_root.glob("*/src"):
            if src_dir.is_dir():
                candidate_paths.append(src_dir)
    added_paths: list[str] = []
    for path in candidate_paths:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
            added_paths.append(path_str)
    try:
        module = importlib.import_module(module_path)
    finally:
        for path_str in added_paths:
            if path_str in sys.path:
                sys.path.remove(path_str)
    factory = getattr(module, symbol, None)
    if factory is None:
        raise RuntimeError(f"Worker symbol {symbol!r} not found in module {module_path!r}")
    worker = factory()
    return cast(PluginWorker, worker)


def _context_envelope(context: ExecutionContext) -> WorkerContextEnvelope:
    return WorkerContextEnvelope(
        workspace_root=context.workspace_root,
        dataset_root=context.dataset_root,
        outputs_root=context.outputs_root,
        logs_root=context.logs_root,
        plugin_root=context.plugin_root,
        bmt_slug=context.bmt_manifest.bmt_slug,
        bmt_id=context.bmt_manifest.bmt_id,
        project_description=context.project_manifest.description,
        execution_policy=context.bmt_manifest.execution.policy,
        execution_profile=context.bmt_manifest.execution.profile,
        runner_template_path=context.bmt_manifest.runner.template_path,
        plugin_config=dict(context.bmt_manifest.plugin_config),
        runner_path=context.runner_path,
        deps_root=context.deps_root,
    )


def execute_worker_plugin(
    *,
    target: WorkerRuntimeTarget,
    context: ExecutionContext,
    baseline: ScoreResult | None = None,
) -> tuple[PreparedAssets, ExecutionResult, ScoreResult, VerdictResult]:
    """Execute plugin worker hooks and return prepared/execution/score/verdict objects."""

    worker = _load_worker(context.plugin_root, target)
    plugin = PluginInvocation(
        project=target.project,
        plugin_id=target.plugin_id,
        plugin_version=target.plugin_version,
    )
    envelope = _context_envelope(context)
    prepared_resp = worker.prepare(PrepareRequest(plugin=plugin, context=envelope))
    prepared_assets = PreparedAssets(
        dataset_root=context.dataset_root,
        workspace_root=context.workspace_root,
        runner_path=context.runner_path,
        extra=dict(prepared_resp.prepared_assets_extra),
    )
    execution_resp = worker.execute(
        ExecuteRequest(
            plugin=plugin,
            context=envelope,
            prepared_assets_extra=dict(prepared_resp.prepared_assets_extra),
        )
    )
    score_resp = worker.score(
        ScoreRequest(
            plugin=plugin,
            context=envelope,
            execution_result=execution_resp.execution_result,
            baseline=baseline,
        )
    )
    verdict_resp = worker.evaluate(
        EvaluateRequest(
            plugin=plugin,
            context=envelope,
            score_result=score_resp.score_result,
            baseline=baseline,
        )
    )
    return prepared_assets, execution_resp.execution_result, score_resp.score_result, verdict_resp.verdict_result
