"""GCS / stage validation for BMT dataset inputs.

Optional pre-flight layer: projects that want fail-fast dataset validation
can declare per-leg manifests as ``projects/<project>/<slug>.json`` in the
materialized stage tree (fields: ``enabled``, ``inputs_prefix``). When present, this module confirms
the declared GCS prefix has the expected ``.wav`` count (cross-checked against
``dataset_manifest.json``) before Cloud Workflows dispatches.

Projects without materialized manifests are **not** misconfigured — the real
BMT leg list is discovered from the project's Python plugin at plan time in
Cloud Run. This validator simply logs a notice and moves on.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cloud_bmt import gcs
from cloud_bmt.actions import gh_notice
from cloud_bmt.config import BmtConfig

_ARCHIVE_PROJECT_SUFFIXES: tuple[str, ...] = (".previous",)


def _project_dir_is_active(project_dir_name: str) -> bool:
    return not any(project_dir_name.endswith(suffix) for suffix in _ARCHIVE_PROJECT_SUFFIXES)


def _stage_root() -> Path:
    configured = (os.environ.get("BMT_STAGE_ROOT") or os.environ.get("BMT_RUNTIME_ROOT") or "").strip()
    if configured:
        return Path(configured)
    for candidate in (Path("generated/stage"), Path("cloud-ci-handoff/generated/stage"), Path("plugins")):
        if candidate.exists():
            return candidate
    return Path("generated/stage")


def _manifest_paths(project_dir: Path) -> list[tuple[str, Path]]:
    if not _project_dir_is_active(project_dir.name):
        return []
    excluded = {"project.json", "plugin-index.json", "runner_latest_meta.json", "runner_meta.json", "runner.slsa.json"}
    flat = sorted(path for path in project_dir.glob("*.json") if path.name not in excluded)
    return [(path.stem, path) for path in flat]


def validate_dataset_inputs(cfg: BmtConfig) -> None:
    """Fail early if any enabled BMT has no .wav files in its GCS inputs prefix."""
    bucket = (cfg.gcs_bucket or "").strip() or os.environ.get("GCS_BUCKET", "")
    if not bucket:
        raise RuntimeError("GCS_BUCKET is not set; cannot validate dataset inputs")
    accepted_raw = (os.environ.get("ACCEPTED_PROJECTS") or "[]").strip()
    accepted_projects: list[str] = json.loads(accepted_raw)
    if not isinstance(accepted_projects, list) or not accepted_projects:
        gh_notice("No accepted projects to validate.")
        return

    stage_root = _stage_root()
    errors: list[str] = []
    for project in accepted_projects:
        project_dir = stage_root / "projects" / project
        if not project_dir.is_dir():
            gh_notice(
                f"{project}: no materialized project dir at {project_dir} — skipping pre-flight dataset "
                "validation (leg list is discovered by the plugin at plan time in Cloud Run)."
            )
            continue
        manifests = _manifest_paths(project_dir)
        if not manifests:
            gh_notice(
                f"{project}: no BMT manifests under {project_dir} — skipping pre-flight dataset validation "
                "(leg list is discovered by the plugin at plan time in Cloud Run)."
            )
            continue
        for bmt_slug, bmt_json_path in manifests:
            payload = json.loads(bmt_json_path.read_text(encoding="utf-8"))
            if not payload.get("enabled", True):
                continue
            inputs_prefix = str(payload.get("inputs_prefix", "")).strip()
            if not inputs_prefix:
                errors.append(f"{project}/{bmt_slug}: bmt.json missing inputs_prefix")
                continue
            prefix_uri = f"gs://{bucket}/{inputs_prefix}/"
            blobs = gcs.list_prefix(prefix_uri)
            wav_count = sum(1 for b in blobs if b.lower().endswith(".wav"))
            manifest_uri = f"gs://{bucket}/{inputs_prefix}/dataset_manifest.json"
            manifest_payload, _ = gcs.download_json(manifest_uri)
            if manifest_payload:
                expected_count = len(manifest_payload.get("files", []))
                if wav_count != expected_count:
                    errors.append(
                        f"{project}/{bmt_slug}: GCS has {wav_count} .wav files but manifest expects {expected_count}"
                    )
                else:
                    gh_notice(f"{project}/{bmt_slug}: {wav_count} .wav file(s) match manifest ✓")
            elif wav_count == 0:
                errors.append(f"{project}/{bmt_slug}: no .wav files found at {prefix_uri}")
            else:
                gh_notice(f"{project}/{bmt_slug}: {wav_count} .wav file(s) at {prefix_uri}")

    if errors:
        for e in errors:
            print(f"::error::{e}")
        raise RuntimeError(
            f"Dataset validation failed: {len(errors)} BMT(s) have empty input datasets.\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
