"""Tests for the bmt_sdk package — no runtime imports allowed."""

from __future__ import annotations

from pathlib import Path

import pytest

# These imports must work without gcp.image installed
from bmt_sdk import BmtPlugin, CloudTaskSpec, ExecutionContext, fail_verdict, pass_verdict
from bmt_sdk.models import (
    BmtManifestView,
    ExecutionConfigView,
    ProjectManifestView,
    RunnerConfigView,
)
from bmt_sdk.results import (
    CaseResult,
    ExecutionResult,
    PreparedAssets,
    ScoreResult,
    VerdictResult,
    VerdictStatus,
)


def _make_context(plugin_config: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        project_manifest=ProjectManifestView(project="test"),
        bmt_manifest=BmtManifestView(
            project="test",
            bmt_slug="test_bmt",
            bmt_id="00000000-0000-0000-0000-000000000001",
            enabled=True,
            plugin_config=plugin_config or {},
        ),
        plugin_root=Path("/fake/plugin"),
        workspace_root=Path("/fake/workspace"),
        dataset_root=Path("/fake/dataset"),
        outputs_root=Path("/fake/outputs"),
        logs_root=Path("/fake/logs"),
    )


def test_custom_plugin_satisfies_bmt_plugin_protocol() -> None:
    from bmt_sdk import averaged_result, custom_plugin

    def execute(context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
        del context, prepared_assets
        return ExecutionResult(execution_mode_used="custom", case_results=[])

    plugin = custom_plugin(project="x", scoring=averaged_result("m"), execute=execute)
    assert isinstance(plugin, BmtPlugin)


def test_incomplete_plugin_object_is_not_bmt_plugin() -> None:
    class Incomplete:
        plugin_name = "x"
        api_version = "v1"
        cloud_task = CloudTaskSpec()

        def prepare(self, context: ExecutionContext) -> PreparedAssets:
            return PreparedAssets(
                dataset_root=context.dataset_root,
                workspace_root=context.workspace_root,
            )

    assert not isinstance(Incomplete(), BmtPlugin)


def test_custom_plugin_valid() -> None:
    from bmt_sdk import averaged_result
    from bmt_sdk.custom import custom_plugin

    def prepare(context: ExecutionContext) -> PreparedAssets:
        return PreparedAssets(
            dataset_root=context.dataset_root,
            workspace_root=context.workspace_root,
        )

    def execute(context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
        return ExecutionResult(execution_mode_used="test", case_results=[])

    def score(
        execution_result: ExecutionResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> ScoreResult:
        return ScoreResult(aggregate_score=1.0)

    def evaluate(
        score_result: ScoreResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> VerdictResult:
        return VerdictResult(passed=True, status="pass", reason_code="ok")

    plugin = custom_plugin(
        project="minimal",
        scoring=averaged_result("score"),
        prepare=prepare,
        execute=execute,
        score=score,
        evaluate=evaluate,
    )
    ctx = _make_context()
    prepared = plugin.prepare(ctx)
    result = plugin.execute(ctx, prepared)
    score_result = plugin.score(result, None, ctx)
    verdict = plugin.evaluate(score_result, None, ctx)
    assert verdict.passed is True
    assert verdict.status == "pass"
    assert isinstance(plugin, BmtPlugin)


def test_custom_plugin_wraps_execute_exceptions() -> None:
    from bmt_sdk import averaged_result, custom_plugin

    def execute(context: ExecutionContext, prepared_assets: PreparedAssets) -> ExecutionResult:
        del context, prepared_assets
        raise RuntimeError("boom")

    def prepare(context: ExecutionContext) -> PreparedAssets:
        return PreparedAssets(
            dataset_root=context.dataset_root,
            workspace_root=context.workspace_root,
        )

    def score(
        execution_result: ExecutionResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> ScoreResult:
        del baseline, context
        return ScoreResult(aggregate_score=0.0, metrics={"case_count": len(execution_result.case_results)})

    def evaluate(
        score_result: ScoreResult,
        baseline: ScoreResult | None,
        context: ExecutionContext,
    ) -> VerdictResult:
        del baseline, context
        return pass_verdict("ok", summary={"aggregate_score": score_result.aggregate_score})

    plugin = custom_plugin(
        project="minimal",
        scoring=averaged_result("score"),
        prepare=prepare,
        execute=execute,
        score=score,
        evaluate=evaluate,
    )
    ctx = _make_context()
    prepared = plugin.prepare(ctx)
    result = plugin.execute(ctx, prepared)
    assert result.raw_summary.get("minimal_plugin_execute_exception") is True
    score_result = plugin.score(result, None, ctx)
    assert score_result.extra.get("minimal_plugin_execute_exception") is True
    verdict = plugin.evaluate(score_result, None, ctx)
    assert verdict.reason_code == "plugin_execute_failed"
    assert not verdict.passed


def test_execution_context_is_frozen() -> None:
    ctx = _make_context()
    with pytest.raises((AttributeError, TypeError)):
        ctx.workspace_root = Path("/other")  # type: ignore[misc]


def test_execution_context_helpers(tmp_path: Path) -> None:
    ctx = ExecutionContext(
        project_manifest=ProjectManifestView(project="test"),
        bmt_manifest=BmtManifestView(
            project="test",
            bmt_slug="test_bmt",
            bmt_id="uuid",
            enabled=True,
            plugin_config={"metric": "score"},
        ),
        plugin_root=tmp_path / "plugin",
        workspace_root=tmp_path / "workspace",
        dataset_root=tmp_path / "dataset",
        outputs_root=tmp_path / "outputs",
        logs_root=tmp_path / "logs",
    )

    assert ctx.plugin_config["metric"] == "score"
    ctx.ensure_output_dirs()
    assert ctx.outputs_root.is_dir()
    assert ctx.logs_root.is_dir()

    dataset_manifest = ctx.dataset_root / "dataset_manifest.json"
    nested_input = ctx.dataset_root / "nested" / "case.wav"
    dataset_manifest.parent.mkdir(parents=True)
    nested_input.parent.mkdir(parents=True)
    dataset_manifest.write_text("{}", encoding="utf-8")
    nested_input.write_text("fake", encoding="utf-8")

    prepared = ctx.prepared_assets()
    assert prepared.dataset_root == ctx.dataset_root
    assert prepared.workspace_root == ctx.workspace_root
    assert prepared.runner_path is None
    assert list(ctx.iter_input_files()) == [nested_input]
    assert list(ctx.iter_input_files(include_dataset_manifest=True)) == [dataset_manifest, nested_input]


def test_bmt_manifest_view_defaults() -> None:
    view = BmtManifestView(
        project="acme",
        bmt_slug="false_alarms",
        bmt_id="uuid",
        enabled=True,
        plugin_config={},
    )
    assert view.execution.policy == "adaptive_batch_then_legacy"
    assert view.runner.uri == ""


def test_sdk_verdict_helpers() -> None:
    passed = pass_verdict("ok", summary={"score": 1.0})
    failed = fail_verdict("below_threshold")

    assert passed.passed is True
    assert passed.status == VerdictStatus.PASS.value
    assert passed.summary["score"] == 1.0
    assert failed.passed is False
    assert failed.status == VerdictStatus.FAIL.value


def test_sdk_package_is_marked_typed() -> None:
    import bmt_sdk

    assert (Path(bmt_sdk.__file__).parent / "py.typed").is_file()


def test_sdk_worker_surface_is_importable_for_ide_completion() -> None:
    from bmt_sdk.worker import (
        PluginCapabilities,
        PluginDescriptor,
        PluginInvocation,
        ensure_abi_compatible,
    )

    descriptor = PluginDescriptor(
        plugin_id="acme.default",
        plugin_slug="default",
        project="acme",
        plugin_version="2.0.0",
        plugin_api_version="2.0",
        entrypoint="acme_default.worker:Worker",
        capabilities=PluginCapabilities(network_profile="none"),
    )
    invocation = PluginInvocation(
        project="acme",
        plugin_id="acme.default",
        plugin_version="2.0.0",
    )
    ensure_abi_compatible(runtime_api_version="2.0", plugin_api_version=descriptor.plugin_api_version)
    assert invocation.plugin_id == "acme.default"


def test_template_plugin_uses_sdk_surface_not_runtime_internals() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugin_source = (repo_root / "examples" / "plugin.py").read_text(encoding="utf-8")

    assert "from runtime." not in plugin_source
    assert "def plugin" in plugin_source
    assert "custom_plugin(" in plugin_source


def test_no_gcp_image_import_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify bmt_sdk has no gcp.image dependency at import time."""
    import importlib
    import sys

    # Remove both gcp.* and bmt_sdk.* from sys.modules so bmt_sdk is fully re-imported
    # from scratch (not served from cache), which would expose any gcp import in sub-modules.
    gcp_modules = [k for k in sys.modules if k.startswith("gcp")]
    bmt_modules = [k for k in sys.modules if k.startswith("bmt_sdk")]
    saved = {k: sys.modules.pop(k) for k in gcp_modules + bmt_modules}
    try:
        import bmt_sdk

        importlib.reload(bmt_sdk)
        # If we reach here, bmt_sdk and all its sub-modules imported without gcp
    finally:
        sys.modules.update(saved)
