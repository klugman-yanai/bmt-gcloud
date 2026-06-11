#!/usr/bin/env python3
"""Strip proprietary Cloud Bench/OEM content and rename to a generic cloud CI template."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DELETE_PATHS = [
    "sdk/bmt_sdk/cloud_bench",
    "sdk/bmt_sdk/cloud_bench_runner_contract.py",
    "runtime/cloud_bench_runparams.py",
    "runtime/cloud_bench_case_metrics.py",
    "runtime/cloud_bench_batch_results.py",
    "runtime/cloud_bench.py",
    "runtime/stdout_counter_parse.py",
    "runtime/assets/cloud_bench_input_template.json",
    "runtime/schemas/krdm_runner_execution_results_v1.schema.json",
    "runtime/schemas/krdm_bmt_case_metrics_v1.schema.json",
    "runtime/schemas/examples/sk_sanity_tests_case.bmt.json.example",
    "tools/scripts/cloud_bench_sandbox_runner.py",
    "tools/scripts/lgtv_verify_stage.py",
    "docs/cloud_bench_runner_SK_runtime.md",
    "docs/bmt-pipeline-signal.md",
    "docs/bmt-adaptation-principles.md",
    "docs/dataset-promotion.md",
    "scripts/build_cloud_bmt_pex.sh",
    "infra/pulumi/bmt.tfvars.json",
    "tests/sk_runner_repo_paths.py",
]

DELETE_GLOBS = [
    "tests/**/test_cloud_bench*.py",
    "tests/**/test_sk_*.py",
    "tests/**/test_lgtv*.py",
    "tests/**/test_skyworth*.py",
    "tests/**/test_*cloud_bench*.py",
    "tests/plugins/**",
    "tests/bmt/test_worker_e2e_*.py",
    "tests/bmt/test_repo_sk_stage.py",
    "tests/bmt/test_lgtv*.py",
    "tests/bmt/test_sk_*.py",
    "tests/bmt/test_cloud_bench*.py",
    "tests/bmt/test_runner_json_input_paths.py",
    "tests/bmt/test_plugin_loader_direct.py",
    "tests/bmt/test_plugin_task_profile.py",
    "tests/bmt/test_observed_duration_snapshot.py",
    "tests/bmt/test_dataset_importer.py",
    "tests/bmt/test_build_plan.py",
    "tests/bmt/test_artifacts_load_summary_or_failure.py",
    "tests/bmt/test_entrypoint_case_digest.py",
    "tests/bmt/test_planning_flat_excludes.py",
    "tests/bmt/test_pr_lifecycle.py",
    "tests/bmt/test_runtime_github_reporting.py",
    "tests/bmt/test_sdk_check_run_copy.py",
    "tests/tools/test_cloud_bench_sandbox_runner.py",
    "tests/tools/test_counter_regex.py",
    "tests/tools/test_upload_runner_dedup.py",
    "tests/tools/test_bucket_bootstrap_runner_meta.py",
    "tests/tools/test_bucket_promote_dataset.py",
    "tests/tools/test_bucket_sync_inputs_guard.py",
    "tests/tools/test_gen_input_manifest.py",
    "tests/tools/test_materialize_projects.py",
    "tests/ci/test_runner_*.py",
    "tests/ci/test_matrix_ci_snapshot_bmt_gcloud.py",
    "tests/ci/test_matrix_core_main.py",
    "tests/ci/test_handoff_dataset.py",
    "tests/ci/test_tag_gate.py",
    "tests/ci/test_baseline_cli.py",
    "tests/sdk/test_cloud_bench*.py",
]

REPLACEMENTS = [
    ("cloud_bmt", "cloud_bmt"),
    ("cloud-bmt", "cloud-bmt"),
    ("Cloud Bench", "Cloud Bench"),
    ("Cloud Bench", "Cloud Bench"),
    ("cloud_bench", "cloud_bench"),
    ("score", "score"),
    ("cloud-ci-handoff", "cloud-ci-handoff"),
    ("Cloud Bench (batch validation pipeline)", "Cloud Bench (batch validation pipeline)"),
    ("batch workloads", "batch workloads"),
    ("input fixtures", "input fixtures"),
    ("quality metric", "quality metric"),
    ("workload plugin", "workload plugin"),
    ("Workload plugin", "Workload plugin"),
    ("runtime/assets/cloud_bench_input_template.json", "runtime/assets/input_template.json"),
]

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".json",
    ".jsonc",
    ".yml",
    ".yaml",
    ".sh",
    ".just",
    ".tf",
    ".example",
    ".env",
    ".txt",
}


def delete_paths() -> None:
    for rel in DELETE_PATHS:
        path = ROOT / rel
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()

    for pattern in DELETE_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink()


def rename_ci_package() -> None:
    src = ROOT / "ci" / "cloud_bmt"
    dst = ROOT / "ci" / "cloud_bmt"
    if src.exists() and not dst.exists():
        src.rename(dst)


def replace_text(path: Path) -> None:
    if path.suffix not in TEXT_SUFFIXES and path.name not in {"justfile", "Justfile", "LICENSE"}:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")


def walk_and_replace() -> None:
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            replace_text(path)


def write_plugin_models() -> None:
    target = ROOT / "sdk" / "bmt_sdk" / "plugin_models.py"
    target.write_text(
        '''"""Strict Pydantic models for plugin configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictPluginModel(BaseModel):
    """Strict immutable base for plugin developer configuration models."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class ManifestConfig(StrictPluginModel):
    """Common validated ``plugin_config`` fields for bench manifests."""

    comparison: str = "gte"
    tolerance_abs: float = Field(default=0.25, ge=0.0)
    run_notes: list[str] = Field(default_factory=list)
    reporting_hints: dict[str, object] = Field(default_factory=dict)


class ScoringPolicyRecord(BaseModel):
    """Validated scoring metadata consumed by reporting and verdict evaluation."""

    model_config = ConfigDict(strict=True, extra="allow", frozen=True)

    comparison: str
    score_direction_hint: str
    score_direction_label: str = Field(min_length=1)
    keyword: str | None = None
    reducer: str | None = None
    failure_policy: str | None = None
    tolerance_abs: float | None = Field(default=None, ge=0.0)

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> ScoringPolicyRecord:
        return cls.model_validate(dict(payload))

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="python")
''',
        encoding="utf-8",
    )


def write_cloud_task_spec() -> None:
    target = ROOT / "sdk" / "bmt_sdk" / "cloud_task_spec.py"
    target.write_text(
        '''"""Cloud Run task sizing declarations for bench tests."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BeforeValidator, Field

from bmt_sdk.plugin_models import StrictPluginModel


class CloudTaskProfile(StrEnum):
    """Cloud Run job memory class for a bench test."""

    STANDARD = "standard"
    HEAVY = "heavy"


class BenchTest(StrEnum):
    """Bench test slug used in manifests, object storage inputs, and plugin overrides."""

    REGRESSION = "regression"
    SMOKE = "smoke"


def _normalize_test_profile_map(value: object) -> object:
    if not isinstance(value, dict):
        return value
    normalized: dict[str, CloudTaskProfile] = {}
    for key, profile in value.items():
        slug = key.value if isinstance(key, BenchTest) else str(key)
        if isinstance(profile, CloudTaskProfile):
            normalized[slug] = profile
        else:
            normalized[slug] = CloudTaskProfile(str(profile))
    return normalized


TestCloudTaskMap = Annotated[dict[str, CloudTaskProfile], BeforeValidator(_normalize_test_profile_map)]


class CloudTaskSpec(StrictPluginModel):
    """Cloud Run task size selection at plan time."""

    default: CloudTaskProfile = Field(default=CloudTaskProfile.STANDARD)
    by_test: TestCloudTaskMap = Field(default_factory=dict)

    def for_slug(self, bmt_slug: str) -> CloudTaskProfile:
        return self.by_test.get(bmt_slug, self.default)


def default_cloud_task(*, heavy_tests: frozenset[BenchTest] = frozenset({BenchTest.REGRESSION})) -> CloudTaskSpec:
    """Default sizing: heavy for selected tests, standard elsewhere."""

    return CloudTaskSpec(by_test=dict.fromkeys(heavy_tests, CloudTaskProfile.HEAVY))
''',
        encoding="utf-8",
    )


def write_scoring() -> None:
    source = ROOT / "sdk" / "bmt_sdk" / "cloud_bench" / "scoring.py"
    if not source.exists():
        return
    text = source.read_text(encoding="utf-8")
    text = text.replace("bmt_sdk.cloud_bench.models", "bmt_sdk.plugin_models")
    text = text.replace("Cloud Bench plugins", "bench plugins")
    text = text.replace("cloud_bench_runner", "custom_plugin")
    text = text.replace("runner_scoring", "custom scoring")
    (ROOT / "sdk" / "bmt_sdk" / "scoring.py").write_text(text, encoding="utf-8")


def patch_sdk_files() -> None:
    plugin = ROOT / "sdk" / "bmt_sdk" / "plugin.py"
    plugin.write_text(
        plugin.read_text(encoding="utf-8").replace(
            "from bmt_sdk.cloud_bench.cloud_task import CloudTaskSpec",
            "from bmt_sdk.cloud_task_spec import CloudTaskSpec",
        ),
        encoding="utf-8",
    )

    custom = ROOT / "sdk" / "bmt_sdk" / "custom.py"
    custom.write_text(
        custom.read_text(encoding="utf-8")
        .replace("from bmt_sdk.cloud_bench.cloud_task import CloudTaskSpec", "from bmt_sdk.cloud_task_spec import CloudTaskSpec")
        .replace("from bmt_sdk.cloud_bench.scoring import ScoringPolicy", "from bmt_sdk.scoring import ScoringPolicy"),
        encoding="utf-8",
    )

    cloud_task = ROOT / "sdk" / "bmt_sdk" / "cloud_task.py"
    cloud_task.write_text(
        cloud_task.read_text(encoding="utf-8").replace(
            "from bmt_sdk.cloud_bench.cloud_task import CloudTaskProfile",
            "from bmt_sdk.cloud_task_spec import CloudTaskProfile",
        ),
        encoding="utf-8",
    )

    init = ROOT / "sdk" / "bmt_sdk" / "__init__.py"
    init.write_text(
        '''"""Stable bench plugin SDK for the cloud CI handoff template."""

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
''',
        encoding="utf-8",
    )


def write_demo_project() -> None:
    demo = ROOT / "projects" / "demo"
    demo.mkdir(parents=True, exist_ok=True)
    (demo / "inputs").mkdir(exist_ok=True)
    (demo / "inputs" / ".keep").write_text("", encoding="utf-8")

    shutil.copy2(ROOT / "examples" / "custom_plugin.py", demo / "plugin.py")
    demo_plugin = demo / "plugin.py"
    demo_plugin.write_text(
        demo_plugin.read_text(encoding="utf-8").replace('project="template-custom"', 'project="demo"'),
        encoding="utf-8",
    )

    manifest = ROOT / "examples" / "project.bmt.json"
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8").replace("template", "demo")
        (demo / "project.bmt.json").write_text(text, encoding="utf-8")


def write_generic_input_template() -> None:
    assets = ROOT / "runtime" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "input_template.json").write_text(
        '{\n  "cases": []\n}\n',
        encoding="utf-8",
    )


def main() -> None:
    write_plugin_models()
    write_cloud_task_spec()
    write_scoring()
    delete_paths()
    rename_ci_package()
    patch_sdk_files()
    write_demo_project()
    write_generic_input_template()
    walk_and_replace()


if __name__ == "__main__":
    main()
