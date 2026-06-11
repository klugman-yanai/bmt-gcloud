"""Pre-dispatch verification of gate bucket readiness (datasets, runners, plugins)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from cloud_bmt import gcs
from cloud_bmt.actions import gh_notice
from cloud_bmt.config import BmtConfig
from cloud_bmt.runner_publish import canonical_runner_object_uris, gate_runner_prefix, runner_publish_layout

_PREPARED_FUSE_TEMP = re.compile(r"#\d+")
_WAV_SUFFIXES = (".wav", ".WAV")


@dataclass(slots=True)
class GateVerifyOptions:
    bucket: str
    projects: list[str]
    stage_root: Path | None = None
    check_prepared_cache: bool = True


@dataclass(slots=True)
class GateVerifyReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def discover_projects_from_checkout(projects_root: Path) -> list[str]:
    """Projects with at least one enabled leg manifest in the checkout tree."""

    if not projects_root.is_dir():
        return []
    discovered: list[str] = []
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name
        for manifest_path in sorted(project_dir.glob("*.json")):
            if manifest_path.name in {"project.json", "plugin-index.json"}:
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not payload.get("enabled", True):
                continue
            if str(payload.get("inputs_prefix", "")).strip():
                discovered.append(project)
                break
    return discovered


def _candidate_project_roots(stage_root: Path | None) -> list[Path]:
    """Directories that may contain ``<project>/`` trees (stage or monorepo checkout)."""

    roots: list[Path] = []
    if stage_root is not None:
        roots.append(stage_root)
    configured = (os.environ.get("BMT_STAGE_ROOT") or os.environ.get("BMT_RUNTIME_ROOT") or "").strip()
    if configured:
        roots.append(Path(configured))
    roots.extend(
        (
            Path("generated/stage"),
            Path("cloud-ci-handoff/generated/stage"),
            Path(".."),  # repo root when cwd is cloud-ci-handoff (CI gate preflight on push)
        )
    )
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def discover_projects_from_gate_bucket(bucket: str) -> list[str]:
    """Projects with ``project.json`` on the gate bucket (push/CI when ACCEPTED_PROJECTS unset)."""

    discovered: list[str] = []
    prefix_uri = _gs_uri(bucket, "projects/")
    for uri in gcs.list_prefix(prefix_uri):
        if not uri.endswith("/project.json"):
            continue
        rel = uri.removeprefix(f"gs://{bucket}/").lstrip("/")
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "projects" and parts[1] and parts[2] == "project.json":
            discovered.append(parts[1])
    return sorted(set(discovered))


def resolve_projects(*, explicit: str | None, stage_root: Path | None, bucket: str | None = None) -> list[str]:
    if explicit:
        raw = explicit.strip()
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise TypeError("projects must be a JSON array")
            return [str(p).strip() for p in parsed if str(p).strip()]
        return [part.strip() for part in raw.split(",") if part.strip()]

    env_raw = (os.environ.get("ACCEPTED_PROJECTS") or "").strip()
    if env_raw:
        parsed = json.loads(env_raw)
        if isinstance(parsed, list) and parsed:
            return [str(p).strip() for p in parsed if str(p).strip()]

    for root in _candidate_project_roots(stage_root):
        projects_dir = root / "projects" if (root / "projects").is_dir() else root
        if not projects_dir.is_dir():
            continue
        checkout_projects = discover_projects_from_checkout(projects_dir)
        if checkout_projects:
            return checkout_projects

    bucket_name = (bucket or os.environ.get("GCS_BUCKET") or "").strip()
    if bucket_name:
        from_bucket = discover_projects_from_gate_bucket(bucket_name)
        if from_bucket:
            return from_bucket
    return []


def _gs_uri(bucket: str, object_path: str) -> str:
    path = object_path.lstrip("/")
    return f"gs://{bucket}/{path}"


def _list_manifest_legs(bucket: str, project: str, stage_root: Path | None) -> list[tuple[str, dict[str, object]]]:
    """Leg manifests from stage checkout when present, else from gate bucket."""

    legs: list[tuple[str, dict[str, object]]] = []
    if stage_root is not None:
        project_dir = stage_root / "projects" / project
        if project_dir.is_dir():
            for path in sorted(project_dir.glob("*.json")):
                if path.name in {"project.json", "plugin-index.json"}:
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    legs.append((path.stem, payload))
            if legs:
                return legs

    prefix_uri = _gs_uri(bucket, f"projects/{project}/")
    for uri in gcs.list_prefix(prefix_uri):
        rel = uri.removeprefix(f"gs://{bucket}/").lstrip("/")
        parts = rel.split("/")
        if len(parts) != 2 or not parts[1].endswith(".json"):
            continue
        slug = Path(parts[1]).stem
        if slug in {"project", "plugin-index", "oem_contract"}:
            continue
        payload, _err = gcs.download_json(uri)
        if isinstance(payload, dict):
            legs.append((slug, payload))
    return legs


def _manifest_missing_files(bucket: str, inputs_prefix: str, manifest_payload: dict[str, object]) -> list[str]:
    missing: list[str] = []
    files = manifest_payload.get("files")
    if not isinstance(files, list):
        return missing
    prefix = inputs_prefix.strip().rstrip("/")
    for entry in files:
        if not isinstance(entry, dict):
            continue
        entry_obj = cast(dict[str, object], entry)
        name = str(entry_obj.get("name", "")).strip()
        if not name:
            continue
        uri = _gs_uri(bucket, f"{prefix}/{name}")
        if not gcs.object_exists(uri):
            missing.append(name)
    return missing


def _wav_count_under_prefix(bucket: str, inputs_prefix: str) -> int:
    prefix_uri = _gs_uri(bucket, f"{inputs_prefix.strip().rstrip('/')}/")
    return sum(1 for uri in gcs.list_prefix(prefix_uri) if uri.lower().endswith(_WAV_SUFFIXES))


def _runner_object_uri(bucket: str, project: str) -> str:
    root = f"gs://{bucket}"
    uris = canonical_runner_object_uris(project, bucket_root=root)
    if runner_publish_layout(project) == "bundle_directory":
        return uris[0]
    return uris[0]


def _object_mode_is_executable(bucket: str, object_path: str) -> bool | None:
    """Return True/False when mode is known; None if metadata unavailable."""

    uri = _gs_uri(bucket, object_path)
    if _which("gcloud") is None:
        return None
    proc = subprocess.run(
        ["gcloud", "storage", "objects", "describe", uri, "--format=json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    custom = payload.get("custom_fields") or payload.get("metadata") or {}
    if isinstance(custom, dict):
        for key, value in custom.items():
            if "mode" in str(key).lower():
                try:
                    mode = int(str(value), 8) if str(value).startswith("0") else int(str(value))
                    return bool(mode & 0o111)
                except ValueError:
                    continue
    return None


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _check_runner(report: GateVerifyReport, *, bucket: str, project: str) -> None:
    uri = _runner_object_uri(bucket, project)
    if not gcs.object_exists(uri):
        report.errors.append(f"{project}: runner missing at {uri}")
        return
    object_path = uri.removeprefix(f"gs://{bucket}/").lstrip("/")
    executable = _object_mode_is_executable(bucket, object_path)
    if executable is False:
        report.errors.append(
            f"{project}: runner at {uri} is not executable on gcsfuse "
            f"(re-upload with gcloud storage cp --preserve-posix; see just lgtv-sync-runner-to-gate)"
        )
    elif executable is True:
        gh_notice(f"{project}: runner executable metadata OK ({uri})")
    else:
        report.warnings.append(f"{project}: could not verify runner POSIX mode at {uri} (gcloud describe unavailable)")
    head_sha = (os.environ.get("HEAD_SHA") or os.environ.get("BMT_RESOLVED_HEAD_SHA") or "").strip()
    if head_sha:
        meta_uri = _gs_uri(bucket, f"projects/{project}/runner_meta.json")
        meta, _ = gcs.download_json(meta_uri)
        if isinstance(meta, dict):
            source_ref = str(meta.get("source_ref", "")).strip()
            if source_ref and source_ref != head_sha:
                gh_notice(
                    f"{project}: gate runner source_ref={source_ref[:12]} differs from "
                    f"HEAD_SHA={head_sha[:12]} (PR will upload CI runner)"
                )


def _check_prepared_cache(report: GateVerifyReport, *, bucket: str, project: str, inputs_prefix: str) -> None:
    prepared_prefix = f"{inputs_prefix.strip().rstrip('/')}/_prepared/"
    prefix_uri = _gs_uri(bucket, prepared_prefix)
    bad: list[str] = []
    for uri in gcs.list_prefix(prefix_uri):
        rel = uri.removeprefix(f"gs://{bucket}/").lstrip("/")
        if _PREPARED_FUSE_TEMP.search(rel):
            bad.append(rel)
    if bad:
        report.warnings.append(
            f"{project}: {len(bad)} corrupt gcsfuse object(s) under _prepared/ "
            f"(remove gs://{bucket}/{prepared_prefix} before re-run; first: {bad[0]})"
        )


def _check_plugin_source(
    report: GateVerifyReport,
    *,
    bucket: str,
    project: str,
    stage_root: Path | None,
) -> None:
    plugin_uri = _gs_uri(bucket, f"projects/{project}/plugin.py")
    stage_plugin = (stage_root / "projects" / project / "plugin.py") if stage_root is not None else None
    if gcs.object_exists(plugin_uri):
        gh_notice(f"{project}: plugin.py OK (bucket)")
    elif stage_plugin is not None and stage_plugin.is_file():
        gh_notice(f"{project}: plugin.py OK (stage)")
    else:
        report.errors.append(f"{project}: plugin.py missing at {plugin_uri}")


def verify_gate_readiness(cfg: BmtConfig, options: GateVerifyOptions) -> GateVerifyReport:
    report = GateVerifyReport()
    if not options.projects:
        report.errors.append("no projects to verify (set ACCEPTED_PROJECTS or --projects)")
        return report

    bucket = options.bucket.strip()
    if not bucket:
        report.errors.append("GCS_BUCKET is not set")
        return report

    bucket_root = f"gs://{bucket}"
    for project in options.projects:
        legs = _list_manifest_legs(bucket, project, options.stage_root)
        if not legs:
            report.warnings.append(
                f"{project}: no leg manifests found on gate or stage — skipping leg checks "
                "(Cloud Run discovers legs from plugin at plan time)"
            )
            continue

        _check_runner(report, bucket=bucket, project=project)
        _check_plugin_source(report, bucket=bucket, project=project, stage_root=options.stage_root)

        enabled_any = False
        for slug, manifest in legs:
            if not manifest.get("enabled", True):
                continue
            enabled_any = True
            inputs_prefix = str(manifest.get("inputs_prefix", "")).strip()
            if not inputs_prefix:
                report.errors.append(f"{project}/{slug}: missing inputs_prefix")
                continue

            wav_count = _wav_count_under_prefix(bucket, inputs_prefix)
            if wav_count == 0:
                report.errors.append(f"{project}/{slug}: no .wav files at gs://{bucket}/{inputs_prefix}/")
                continue

            gh_notice(f"{project}/{slug}: {wav_count} .wav file(s) at gs://{bucket}/{inputs_prefix}/")

            manifest_uri = _gs_uri(bucket, f"{inputs_prefix.rstrip('/')}/dataset_manifest.json")
            manifest_payload, _ = gcs.download_json(manifest_uri)
            if manifest_payload and isinstance(manifest_payload.get("files"), list):
                missing = _manifest_missing_files(bucket, inputs_prefix, manifest_payload)
                if missing:
                    report.warnings.append(
                        f"{project}/{slug}: dataset_manifest lists {len(missing)} missing object(s), first={missing[0]}"
                    )

            if options.check_prepared_cache and project == "sk" and "false_rejects" in slug:
                _check_prepared_cache(report, bucket=bucket, project=project, inputs_prefix=inputs_prefix)

        if not enabled_any:
            report.warnings.append(f"{project}: no enabled legs in manifests")

        _ = bucket_root  # referenced for side-effect free lint
        _ = gate_runner_prefix(project)

    return report


def run_verify(
    cfg: BmtConfig,
    *,
    projects: list[str] | None = None,
    projects_csv: str | None = None,
    stage_root: Path | None = None,
    check_prepared_cache: bool = True,
) -> None:
    bucket = (cfg.gcs_bucket or "").strip() or os.environ.get("GCS_BUCKET", "")
    resolved = projects or resolve_projects(
        explicit=projects_csv,
        stage_root=stage_root,
        bucket=bucket,
    )
    report = verify_gate_readiness(
        cfg,
        GateVerifyOptions(
            bucket=bucket,
            projects=resolved,
            stage_root=stage_root,
            check_prepared_cache=check_prepared_cache,
        ),
    )
    for warning in report.warnings:
        print(f"::warning::{warning}")
    if report.errors:
        for err in report.errors:
            print(f"::error::{err}")
        raise RuntimeError(
            f"Gate verify failed: {len(report.errors)} error(s)\n" + "\n".join(f"  - {e}" for e in report.errors)
        )
    gh_notice(f"Gate verify passed for {', '.join(resolved)} on gs://{bucket}")
