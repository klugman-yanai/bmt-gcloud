"""Validate, materialize, and optionally sync a root Cloud BMT project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime.models import BmtManifest, ProjectManifest
from runtime.plugin_loader import load_plugin_direct
from runtime.plugin_publisher import plugin_digest
from tools.bmt.materialize import materialize_projects
from tools.bmt.project_bundle import BUNDLE_MANIFEST_NAME, load_project_bundle
from tools.bmt.project_sources import project_source_dir
from tools.remote.bucket_sync_project import BucketSyncProject
from tools.repo.paths import DEFAULT_STAGE_ROOT, repo_root
from tools.shared.bucket_env import bucket_from_env


@dataclass(frozen=True, slots=True)
class ProjectPublishResult:
    project: str
    digest: str
    source_dir: Path
    stage_dir: Path


def _source_project_dir(project: str, source_root: Path | None = None) -> Path:
    return project_source_dir(source_root, project)


def _stage_root(stage_root: Path | None) -> Path:
    return stage_root if stage_root is not None else repo_root() / DEFAULT_STAGE_ROOT


def _load_bmt_manifest(project_dir: Path, *, project: str, bmt_slug: str) -> BmtManifest:
    bundle_path = project_dir / BUNDLE_MANIFEST_NAME
    bundle = load_project_bundle(bundle_path)
    try:
        data = bundle.bmts[bmt_slug]
    except KeyError as exc:
        raise FileNotFoundError(f"BMT {project}/{bmt_slug} does not exist in {bundle_path}") from exc
    return BmtManifest.model_validate(data)


def validate_project_source(*, project: str, bmt_slug: str, source_root: Path | None = None) -> str:
    project_dir = _source_project_dir(project, source_root)
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Cloud BMT project does not exist: {project_dir}")
    bundle_path = project_dir / BUNDLE_MANIFEST_NAME
    project_manifest = ProjectManifest.model_validate(load_project_bundle(bundle_path).project)
    if project_manifest.project != project:
        raise ValueError(
            f"{bundle_path} declares project={project_manifest.project!r}, expected {project!r}"
        )
    bmt_manifest = _load_bmt_manifest(project_dir, project=project, bmt_slug=bmt_slug)
    if bmt_manifest.project != project:
        raise ValueError(
            f"{bundle_path} BMT {bmt_slug!r} declares project={bmt_manifest.project!r}, expected {project!r}"
        )
    load_plugin_direct(project_dir)
    return plugin_digest(project_dir)


def sync_project(*, bucket: str, project: str, stage_root: Path | None = None) -> int:
    return BucketSyncProject().run(bucket=bucket, project=project, stage_root=stage_root)


def publish_bmt(
    *,
    source_root: Path | None = None,
    stage_root: Path | None = None,
    project: str,
    bmt_slug: str,
    sync: bool = True,
) -> ProjectPublishResult:
    """Validate root project source, materialize it, and optionally sync its stage subtree."""
    source_dir = _source_project_dir(project, source_root)
    digest = validate_project_source(project=project, bmt_slug=bmt_slug, source_root=source_root)
    resolved_stage_root = _stage_root(stage_root)
    materialize_projects(source_root=source_root, stage_root=resolved_stage_root, clean=False)
    stage_dir = resolved_stage_root / "projects" / project
    if not stage_dir.is_dir():
        raise RuntimeError(f"Project {project!r} was not materialized into {stage_dir}")

    if sync:
        bucket = bucket_from_env()
        if not bucket:
            raise RuntimeError("Unable to resolve GCS_BUCKET from env or GitHub repo vars")
        rc = sync_project(bucket=bucket, project=project, stage_root=resolved_stage_root)
        if rc != 0:
            raise RuntimeError(f"Failed to sync project {project} to gs://{bucket}")

    return ProjectPublishResult(
        project=project,
        digest=digest,
        source_dir=source_dir,
        stage_dir=stage_dir,
    )
