"""Build immutable execution plans from staged manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from runtime.models import (
    BmtManifest,
    ExecutionPlan,
    PlanLeg,
    ProjectManifest,
    StageRuntimePaths,
    WorkflowRequest,
)
from runtime.plugin_contract import resolve_plugin_id, resolve_plugin_version
from runtime.plugin_publisher import plugin_digest
from runtime.plugin_task_profile import resolve_leg_execution_profile

# Archive / rollback trees under projects/ must not register legs.
_ARCHIVE_PROJECT_SUFFIXES: tuple[str, ...] = (".previous",)


@dataclass(frozen=True, slots=True)
class PlanOptions:
    request: WorkflowRequest
    allow_workspace_plugins: bool = False


_FLAT_EXCLUDE: frozenset[str] = frozenset(
    {
        "project.json",
        "project.bmt.json",
        "runner_latest_meta.json",
        "runner_meta.json",
        "runner.slsa.json",
        "plugin-index.json",
    }
)


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_flat_bmt_manifest(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    return isinstance(data, dict) and "bmt_id" in data


def _project_dir_is_active(project_dir_name: str) -> bool:
    return not any(project_dir_name.endswith(suffix) for suffix in _ARCHIVE_PROJECT_SUFFIXES)


def _discover_bmt_manifests(projects_root: Path) -> list[tuple[Path, BmtManifest]]:
    """Discover generated flat BMT manifests (``projects/<project>/<bmt>.json``)."""
    manifests: list[tuple[Path, BmtManifest]] = []
    for manifest_path in sorted(projects_root.glob("*/*.json")):
        project_dir = manifest_path.parent.name
        if not _project_dir_is_active(project_dir):
            continue
        if manifest_path.name in _FLAT_EXCLUDE or manifest_path.name.startswith("_"):
            continue
        if not _is_flat_bmt_manifest(manifest_path):
            continue
        manifests.append((manifest_path, BmtManifest.from_flat_file(manifest_path)))
    return manifests


def build_plan(*, runtime: StageRuntimePaths, options: PlanOptions) -> ExecutionPlan:
    legs: list[PlanLeg] = []
    projects_root = runtime.stage_root / "projects"
    accepted_projects = {project for project in options.request.accepted_projects if project}
    for manifest_path, bmt_manifest in _discover_bmt_manifests(projects_root):
        if not bmt_manifest.enabled:
            continue
        if accepted_projects and bmt_manifest.project not in accepted_projects:
            continue
        project_manifest_path = projects_root / bmt_manifest.project / "project.json"
        _ = ProjectManifest.model_validate(json.loads(project_manifest_path.read_text(encoding="utf-8")))
        plugin_root = projects_root / bmt_manifest.project
        run_id = f"{options.request.workflow_run_id}-{bmt_manifest.bmt_slug}"
        execution_profile = resolve_leg_execution_profile(
            stage_root=runtime.stage_root,
            project=bmt_manifest.project,
            bmt_slug=bmt_manifest.bmt_slug,
            manifest_profile=bmt_manifest.execution.profile,
        )
        legs.append(
            PlanLeg(
                project=bmt_manifest.project,
                bmt_slug=bmt_manifest.bmt_slug,
                bmt_id=bmt_manifest.bmt_id,
                run_id=run_id,
                execution_profile=execution_profile,
                manifest_path=str(manifest_path.relative_to(runtime.stage_root)),
                manifest_digest=_file_digest(manifest_path),
                plugin_ref=bmt_manifest.plugin_ref,
                plugin_id=resolve_plugin_id(bmt_manifest.project, bmt_manifest.plugin_id),
                plugin_version=resolve_plugin_version(bmt_manifest.plugin_version),
                plugin_digest=plugin_digest(plugin_root),
                inputs_prefix=bmt_manifest.inputs_prefix,
                results_path=bmt_manifest.results_path,
                outputs_prefix=bmt_manifest.outputs_prefix,
            )
        )
    seen_results_paths: dict[str, str] = {}
    for leg in legs:
        key = leg.results_path
        if key in seen_results_paths:
            raise ValueError(
                f"Duplicate results_path {key!r}: legs {seen_results_paths[key]!r} and "
                f"{leg.project!r}/{leg.bmt_slug!r} both write to the same path. "
                "Each enabled BMT must have a unique results_path."
            )
        seen_results_paths[key] = f"{leg.project}/{leg.bmt_slug}"
    standard_task_count = sum(1 for leg in legs if leg.execution_profile == "standard")
    heavy_task_count = sum(1 for leg in legs if leg.execution_profile == "heavy")
    return ExecutionPlan(
        workflow_run_id=options.request.workflow_run_id,
        repository=options.request.repository,
        head_sha=options.request.head_sha,
        head_branch=options.request.head_branch,
        head_event=options.request.head_event,
        pr_number=options.request.pr_number,
        run_context=options.request.run_context,
        accepted_projects=sorted(accepted_projects),
        status_context=options.request.status_context,
        active_generation=options.request.active_generation,
        standard_task_count=standard_task_count,
        heavy_task_count=heavy_task_count,
        legs=legs,
    )
