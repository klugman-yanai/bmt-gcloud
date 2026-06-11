"""Execute BmtPlugin hooks in-process from ``plugin.py``."""

from __future__ import annotations

from pathlib import Path

from bmt_sdk.context import ExecutionContext
from bmt_sdk.results import ExecutionResult, PreparedAssets, ScoreResult, VerdictResult

from runtime.plugin_loader import load_plugin_direct


def execute_plugin_direct(
    *,
    project_dir: Path,
    context: ExecutionContext,
    baseline: ScoreResult | None = None,
) -> tuple[PreparedAssets, ExecutionResult, ScoreResult, VerdictResult]:
    """Run prepare → execute → score → evaluate on the project's ``plugin.py`` plugin."""

    plugin, _plugin_dir = load_plugin_direct(project_dir)
    prepared = plugin.prepare(context)
    execution = plugin.execute(context, prepared)
    score = plugin.score(execution, baseline, context)
    verdict = plugin.evaluate(score, baseline, context)
    return prepared, execution, score, verdict
