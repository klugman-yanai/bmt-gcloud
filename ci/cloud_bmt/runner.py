"""Runner: upload to GCS, validate in repo, filter upload matrix, resolve uploaded, summarize."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

from whenever import Instant

from cloud_bmt import config, core, gcs
from cloud_bmt.actions import gh_notice, gh_warning, write_github_output
from cloud_bmt.config import BmtConfig, BmtContext, WorkflowContext
from cloud_bmt.runner_provenance import write_runner_provenance
from cloud_bmt.runner_publish import (
    canonical_runner_object_uris,
    gate_runner_prefix,
    iter_bundle_files,
    runner_publish_layout,
    runner_publish_section,
)
from cloud_bmt.workflow_env import read_workflow_str


_FLAT_BMT_EXCLUDE: frozenset[str] = frozenset(
    {
        "project.json",
        "runner_latest_meta.json",
        "runner_meta.json",
        "runner.slsa.json",
    }
)


def _project_has_bmt_bucket_layout(root: str, project: str) -> bool:
    """True when the authenticated BMT bucket declares at least one BMT for ``project``."""
    slug = str(project).strip().lower()
    if not slug:
        return False
    prefix = f"{root}/projects/{slug}/"
    uris = gcs.list_prefix(prefix)
    for uri in uris:
        rel = uri.removeprefix(prefix)
        name = rel.rsplit("/", 1)[-1]
        if "/" not in rel and name.endswith(".json") and name not in _FLAT_BMT_EXCLUDE and not name.startswith("_"):
            return True
    return False


def _normalize_run_notes(raw: object) -> list[str]:
    if isinstance(raw, str):
        candidates: list[object] = [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []
    notes: list[str] = []
    for value in candidates:
        if not isinstance(value, str):
            continue
        note = value.strip()
        if note:
            notes.append(note)
    return notes


def _project_run_notes_in_gcs(root: str, project: str) -> list[str]:
    slug = str(project).strip().lower()
    if not slug:
        return []
    prefix = f"{root}/projects/{slug}/"
    notes: list[str] = []
    seen: set[str] = set()
    for uri in gcs.list_prefix(prefix):
        rel = uri.removeprefix(prefix)
        name = rel.rsplit("/", 1)[-1]
        is_manifest = (
            "/" not in rel and name.endswith(".json") and name not in _FLAT_BMT_EXCLUDE and not name.startswith("_")
        )
        if not is_manifest:
            continue
        payload, _ = gcs.download_json(uri)
        if not isinstance(payload, dict):
            continue
        plugin_config = payload.get("plugin_config")
        if not isinstance(plugin_config, dict):
            continue
        bmt_slug = str(payload.get("bmt_slug") or Path(name).stem).strip()
        for note in _normalize_run_notes(plugin_config.get("run_notes")):
            key = f"{bmt_slug}\0{note}"
            if key in seen:
                continue
            seen.add(key)
            notes.append(f"`{bmt_slug}`: {note}" if bmt_slug else note)
    return notes


def _runner_meta_in_gcs(root: str, project: str, preset: str) -> dict[str, Any] | None:
    # New layout: projects/{project}/{meta}
    for name in ("runner_meta.json", "runner_latest_meta.json"):
        payload, _ = gcs.download_json(f"{root}/projects/{project}/{name}")
        if isinstance(payload, dict):
            return payload
    # Old layout (bucket_upload_runner.py): {project}/runners/{preset}/{meta}
    payload, _ = gcs.download_json(f"{root}/{project}/runners/{preset}/runner_latest_meta.json")
    if isinstance(payload, dict):
        return payload
    return None


def _runner_binary_exists_in_gcs(root: str, project: str, preset: str) -> bool:
    check_uris = [
        uri.replace("{preset}", preset)
        for uri in canonical_runner_object_uris(project, bucket_root=root)
    ]
    for uri in check_uris:
        try:
            if gcs.object_exists(uri):
                return True
        except gcs.GcsError:
            pass
    return False


def _ci_run_id_for_markers() -> str:
    """Prefer parent CI run id (``BMT_CI_RUN_ID``) so GCS markers align with build-and-test."""
    rid = (os.environ.get("BMT_CI_RUN_ID") or "").strip()
    return rid or core.workflow_run_id()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_runner_file(local_path: Path, dest_uri: str, *, executable: bool) -> None:
    """Upload a runner artifact; prefer ``gcloud storage cp --preserve-posix`` when available."""

    mode = local_path.stat().st_mode
    if executable or (mode & 0o111):
        with contextlib.suppress(OSError):
            local_path.chmod(mode | 0o111)
        if shutil.which("gcloud"):
            proc = subprocess.run(
                ["gcloud", "storage", "cp", "--preserve-posix", str(local_path), dest_uri],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return
    gcs.write_object(dest_uri, local_path.read_bytes())


def _rotate_gate_runner_prefix(bucket_root: str, gate_prefix: str) -> None:
    """Copy current gate runner tree to ``{gate_prefix}.previous`` before tag publish."""
    src_prefix = f"{bucket_root.rstrip('/')}/{gate_prefix.strip('/')}/"
    dest_prefix = f"{bucket_root.rstrip('/')}/{gate_prefix.strip('/')}.previous/"
    try:
        existing = gcs.list_prefix(src_prefix)
    except gcs.GcsError as exc:
        gh_warning(f"Could not list {src_prefix} for rotation: {exc}")
        return
    if not existing:
        return
    try:
        for uri in gcs.list_prefix(dest_prefix):
            gcs.delete_object(uri)
    except gcs.GcsError as exc:
        gh_warning(f"Could not clear {dest_prefix}: {exc}")
    copied = 0
    for uri in existing:
        rel = uri.removeprefix(src_prefix)
        if not rel or rel == "results" or rel.startswith("results/"):
            continue
        try:
            gcs.copy_object(uri, f"{dest_prefix}{rel}")
            copied += 1
        except gcs.GcsError as exc:
            gh_warning(f"Could not copy {uri} to previous: {exc}")
    gh_notice(f"Rotated {copied} object(s) under {gate_prefix} → {gate_prefix}.previous")


def _require_nonempty_file(path: Path, *, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"{label} not found: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RuntimeError(f"{label} is empty (placeholder artifact refused): {path}")


def _write_matrix_output(f, name: str, value: dict[str, Any], heredoc_label: str) -> None:
    """Emit a heredoc-wrapped matrix output for ``$GITHUB_OUTPUT``."""
    body = json.dumps(value, separators=(",", ":"))
    f.write(f"{name}<<{heredoc_label}\n{body}\n{heredoc_label}\n")


def _runner_artifact_candidates(entry: dict[str, Any], preset: str) -> list[str]:
    raw = [
        entry.get("artifact_name"),
        f"runner-{entry.get('build')}" if str(entry.get("build", "")).strip() else "",
        f"runner-{entry.get('build_preset')}" if str(entry.get("build_preset", "")).strip() else "",
        f"runner-{entry.get('configure')}-build" if str(entry.get("configure", "")).strip() else "",
        f"runner-{entry.get('configure_preset')}-build" if str(entry.get("configure_preset", "")).strip() else "",
        f"runner-{preset}",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _match_runner_artifact(entry: dict[str, Any], preset: str, artifact_set: set[str]) -> str | None:
    candidates = _runner_artifact_candidates(entry, preset)
    for candidate in candidates:
        if candidate in artifact_set:
            return candidate
    by_lower = {name.lower(): name for name in artifact_set}
    for candidate in candidates:
        match = by_lower.get(candidate.lower())
        if match:
            return match
    return None


def _render_matrix_step_summary(
    publish_include: list[dict[str, Any]],
    no_bmt_include: list[dict[str, Any]],
) -> str:
    """Render one aggregated Markdown section for the Plan job's step summary.

    Replaces per-leg ``$GITHUB_STEP_SUMMARY`` writes in the ``Publish`` and
    ``No BMT`` matrix jobs with a single table, so the run summary stays
    readable even with 12 release presets.
    """
    lines: list[str] = ["## BMT matrix", ""]

    lines.append(f"### Publish ({len(publish_include)} leg(s))")
    lines.append("")
    if publish_include:
        lines.append("| project | preset | action | reason |")
        lines.append("| --- | --- | --- | --- |")
        for row in publish_include:
            project = str(row.get("project", ""))
            preset = str(row.get("preset", ""))
            action = str(row.get("upload_action", ""))
            reason = str(row.get("skip_reason", "") or "")
            lines.append(f"| {project} | {preset} | `{action}` | {reason} |")
    else:
        lines.append("_No supported BMT legs — nothing to dispatch._")
    lines.append("")

    lines.append(f"### No BMT ({len(no_bmt_include)} leg(s))")
    lines.append("")
    if no_bmt_include:
        lines.append("| project | preset | reason |")
        lines.append("| --- | --- | --- |")
        for row in no_bmt_include:
            project = str(row.get("project", ""))
            preset = str(row.get("preset", ""))
            reason = str(row.get("skip_reason", "") or "no BMT manifest in authenticated bucket")
            lines.append(f"| {project} | {preset} | {reason} |")
    else:
        lines.append("_All release presets are supported — no acknowledgement rows._")
    lines.append("")

    run_note_lines: list[str] = []
    for row in publish_include:
        project = str(row.get("project", ""))
        for note in _normalize_run_notes(row.get("run_notes")):
            run_note_lines.append(f"- **{project}:** {note}")
    if run_note_lines:
        lines.append("### Run notes")
        lines.append("")
        lines.extend(run_note_lines)
        lines.append("")

    return "\n".join(lines)


def _append_matrix_step_summary(markdown: str) -> None:
    """Append to ``$GITHUB_STEP_SUMMARY`` when present; no-op locally."""
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(markdown)


def filter_bmt_presets_upstream_artifacts_matrix(
    artifact_root: Path, repo_root: Path
) -> tuple[list[dict[str, Any]], int, bool]:
    """Build a handoff matrix from uploaded runner metadata."""
    items: list[dict[str, Any]] = []
    for meta_path in sorted(artifact_root.resolve().glob("*/metadata.json")):
        with meta_path.open(encoding="utf-8") as fh:
            metadata = json.load(fh)
        if not metadata.get("runnable_on_bmt_runner", False):
            continue
        build_preset = metadata["build_preset"]
        bmt_key = metadata.get("bmt_key", build_preset)
        items.append(
            {
                "artifact_name": f"runner-{build_preset}",
                "build_preset": build_preset,
                "bmt_key": bmt_key,
                "configure_preset": metadata["configure_preset"],
                "runner_path": metadata["runner_path"],
                "arch": metadata.get("arch", ""),
                "os": metadata.get("os", ""),
            }
        )
    n = len(items)
    return items, n, n > 0


class RunnerManager:
    def __init__(self, cfg: BmtConfig, ctx: BmtContext | None) -> None:
        self._cfg = cfg
        self._ctx = ctx

    @classmethod
    def from_env(cls) -> RunnerManager:
        return cls(config.get_config(), config.get_context())

    def _w(self) -> WorkflowContext | None:
        return self._ctx.workflow if self._ctx else None

    def validate_in_repo(self) -> None:
        project = core.require_env("PROJECT")
        run_id = _ci_run_id_for_markers()
        root = core.workflow_runtime_root()
        check_uris = canonical_runner_object_uris(project, bucket_root=root)
        check_uris.append(f"{root}/{project}/runners/{core.require_env('PRESET')}/cloud_bench_runner")
        exists = False
        found_uri = ""
        for uri in check_uris:
            if "{preset}" in uri:
                continue
            try:
                if gcs.object_exists(uri):
                    exists = True
                    found_uri = uri
                    break
            except gcs.GcsError as exc:
                print(f"::warning::Could not verify runner in GCS ({exc}).")
        if exists:
            print(f"::notice::Requested runner exists in bucket: {found_uri} (validated for handoff).")
        else:
            gh_warning(
                "VM does not support this BMT: requested runner not found in bucket at "
                f"{check_uris[0]}. Runner binaries are bucket artifacts and are not committed to the suite repo. "
                "No handoff leg will run for this project."
            )
            return
        marker_uri = f"{root}/_workflow/uploaded/{run_id}/{project}.json"
        try:
            gcs.write_object(marker_uri, "{}")
        except gcs.GcsError as exc:
            raise RuntimeError(f"Failed to write uploaded marker {marker_uri}: {exc}") from exc
        print(f"Marked project {project} as validated for handoff -> {marker_uri}")

    def filter_upload_matrix(self) -> None:
        """Classify every release preset into one of three UI buckets.

        Outputs three matrices that the workflow renders as two parallel job nodes:

        - ``matrix_publish``  — supported BMT legs (one row per preset with an
          ``upload_action`` field: ``upload`` means a real GCS push is needed;
          ``skip_in_gcs`` means the runner is already in the bucket so the job
          only records "Skipped (already in GCS)" for visibility).
        - ``matrix_no_bmt``   — release presets whose project has no BMT
          manifest in the authenticated bucket; rendered as an informational "Acknowledged (no BMT)"
          parallel matrix, never red.
        - ``matrix_need_upload`` (back-compat) — subset of ``matrix_publish``
          where ``upload_action == 'upload'``. Downstream readers that only
          care about real uploads keep working unchanged.
        """
        w = self._w()
        skip_publish = read_workflow_str(w, "bmt_skip_publish_runners", "BMT_SKIP_PUBLISH_RUNNERS").lower() in (
            "1",
            "true",
            "yes",
        )
        empty: dict[str, Any] = {"include": []}
        if skip_publish:
            path = Path(core.require_env("GITHUB_OUTPUT"))
            with path.open("a", encoding="utf-8") as f:
                _write_matrix_output(f, "matrix_need_upload", empty, "FILTER_EOF")
                f.write("matrix_need_upload_keys=[]\n")
                _write_matrix_output(f, "matrix_publish", empty, "PUBLISH_EOF")
                f.write("matrix_publish_keys=[]\n")
                _write_matrix_output(f, "matrix_no_bmt", empty, "NOBMT_EOF")
                f.write("matrix_no_bmt_keys=[]\n")
            print(
                "::notice::Filter upload matrix: BMT_SKIP_PUBLISH_RUNNERS=true — no publish jobs (runners assumed in bucket)."
            )
            _append_matrix_step_summary(_render_matrix_step_summary([], []))
            return
        runner_matrix_raw = read_workflow_str(w, "runner_matrix", "RUNNER_MATRIX")
        head_sha = read_workflow_str(w, "head_sha", "HEAD_SHA")
        preseeded = read_workflow_str(w, "bmt_runners_preseeded_in_gcs", "BMT_RUNNERS_PRESEEDED_IN_GCS").lower() in (
            "1",
            "true",
            "yes",
        )
        available_artifacts_raw = read_workflow_str(w, "available_artifacts", "AVAILABLE_ARTIFACTS", "[]")
        github_run_id = (os.environ.get("BMT_CI_RUN_ID") or "").strip() or (
            read_workflow_str(w, "github_run_id", "GITHUB_RUN_ID") or core.workflow_run_id()
        )
        if not runner_matrix_raw or not head_sha:
            raise RuntimeError("RUNNER_MATRIX and HEAD_SHA are required")
        matrix = json.loads(runner_matrix_raw)
        include = matrix.get("include", [])
        if not isinstance(include, list):
            raise TypeError("RUNNER_MATRIX.include must be a JSON array")
        try:
            available_artifacts = json.loads(available_artifacts_raw)
        except json.JSONDecodeError:
            available_artifacts = []
        artifact_set = {
            str(a).strip()
            for a in (available_artifacts if isinstance(available_artifacts, list) else [])
            if str(a).strip()
        }
        root = core.workflow_runtime_root()
        run_id = github_run_id
        publish_include: list[dict[str, Any]] = []
        no_bmt_include: list[dict[str, Any]] = []
        projects_written: set[str] = set()
        support_cache: dict[str, bool] = {}
        notes_cache: dict[str, list[str]] = {}
        for entry in include:
            if not isinstance(entry, dict):
                continue
            project = str(entry.get("project", "")).strip()
            preset = str(entry.get("preset", "")).strip()
            if not project or not preset:
                continue
            if project not in support_cache:
                try:
                    support_cache[project] = _project_has_bmt_bucket_layout(root, project)
                except gcs.GcsError as exc:
                    raise RuntimeError(f"Failed to probe BMT bucket support for project {project!r}: {exc}") from exc
            supported = support_cache[project]

            if not supported:
                row = cast(dict[str, Any], dict(entry))
                row["bmt_supported"] = "false"
                row["upload_action"] = "no_bmt"
                row["skip_reason"] = "no BMT manifest in authenticated bucket"
                no_bmt_include.append(row)
                continue

            action, reason = self._classify_supported_leg(
                root=root,
                project=project,
                preset=preset,
                entry=entry,
                head_sha=head_sha,
                preseeded=preseeded,
                artifact_set=artifact_set,
            )
            if action == "skip_in_gcs" and project not in projects_written:
                marker_uri = f"{root}/_workflow/uploaded/{run_id}/{project}.json"
                try:
                    gcs.write_object(marker_uri, "{}")
                except gcs.GcsError as e:
                    gh_warning(f"Could not write uploaded marker {marker_uri}: {e}")
                projects_written.add(project)

            row = cast(dict[str, Any], dict(entry))
            row["bmt_supported"] = "true"
            row["upload_action"] = action
            row["skip_reason"] = reason
            if action == "upload":
                artifact_name = _match_runner_artifact(row, preset, artifact_set)
                if artifact_name:
                    row["artifact_name"] = artifact_name
            if project not in notes_cache:
                try:
                    notes_cache[project] = _project_run_notes_in_gcs(root, project)
                except gcs.GcsError as exc:
                    gh_warning(f"Could not read BMT run notes for {project}: {exc}")
                    notes_cache[project] = []
            if notes_cache[project]:
                row["run_notes"] = notes_cache[project]
            publish_include.append(row)
            print(
                f"::notice::{project}/{preset}: bmt_supported=true upload_action={action}"
                + (f" ({reason})" if reason else "")
            )

        need_include = [
            {k: v for k, v in e.items() if k not in ("bmt_supported", "upload_action", "skip_reason")}
            for e in publish_include
            if e.get("upload_action") == "upload"
        ]
        path = Path(core.require_env("GITHUB_OUTPUT"))
        with path.open("a", encoding="utf-8") as f:
            _write_matrix_output(f, "matrix_need_upload", {"include": need_include}, "FILTER_EOF")
            f.write(f"matrix_need_upload_keys={json.dumps([f'{e["project"]}|{e["preset"]}' for e in need_include])}\n")
            _write_matrix_output(f, "matrix_publish", {"include": publish_include}, "PUBLISH_EOF")
            f.write(f"matrix_publish_keys={json.dumps([f'{e["project"]}|{e["preset"]}' for e in publish_include])}\n")
            _write_matrix_output(f, "matrix_no_bmt", {"include": no_bmt_include}, "NOBMT_EOF")
            f.write(f"matrix_no_bmt_keys={json.dumps([f'{e["project"]}|{e["preset"]}' for e in no_bmt_include])}\n")
        blocked = [e for e in publish_include if e.get("upload_action") == "blocked"]
        if blocked:
            detail = "; ".join(f"{e.get('project')}/{e.get('preset')}: {e.get('skip_reason', '')}" for e in blocked)
            raise RuntimeError(f"Runner handoff blocked — {detail}")

        n_upload = sum(1 for e in publish_include if e.get("upload_action") == "upload")
        n_skip_in_gcs = sum(1 for e in publish_include if e.get("upload_action") == "skip_in_gcs")
        print(
            f"::notice::Filter upload matrix: "
            f"{len(publish_include)} supported leg(s) ({n_upload} upload, {n_skip_in_gcs} already in GCS); "
            f"{len(no_bmt_include)} release preset(s) with no BMT manifest in the authenticated bucket."
        )
        _append_matrix_step_summary(_render_matrix_step_summary(publish_include, no_bmt_include))

    def _classify_supported_leg(
        self,
        *,
        root: str,
        project: str,
        preset: str,
        entry: dict[str, Any],
        head_sha: str,
        preseeded: bool,
        artifact_set: set[str],
    ) -> tuple[str, str]:
        """Decide whether a supported leg needs to upload or can reuse what's in GCS.

        Returns ``(upload_action, skip_reason)`` — ``upload``, ``skip_in_gcs``, or ``blocked``.
        """
        if not artifact_set:
            payload = _runner_meta_in_gcs(root, project, preset)
            if payload is not None:
                reason = (
                    "preseeded"
                    if preseeded
                    else (
                        f"meta source_ref matches {head_sha[:7]}"
                        if str(payload.get("source_ref", "")).strip() == head_sha
                        else "no GitHub artifacts from caller"
                    )
                )
                return "skip_in_gcs", f"runner in GCS ({reason})"
            if _runner_binary_exists_in_gcs(root, project, preset):
                return "skip_in_gcs", "runner binary in GCS"
            return (
                "blocked",
                f"missing GCS runner for {project}/{preset}; seed the bucket runner before handoff",
            )

        artifact_name = _match_runner_artifact(entry, preset, artifact_set)
        if artifact_name is None:
            expected = ", ".join(_runner_artifact_candidates(entry, preset))
            return "blocked", f"missing runner artifact in caller CI artifacts (tried {expected})"

        payload = _runner_meta_in_gcs(root, project, preset)
        if payload is not None and str(payload.get("source_ref", "")).strip() == head_sha:
            return "skip_in_gcs", f"runner in GCS (meta source_ref matches {head_sha[:7]})"

        return "upload", ""

    def _collect_flat_upload_files(self, *, project: str, bucket_root: str) -> list[dict[str, Any]]:
        runner_dir = Path(os.environ.get("RUNNER_DIR", "artifact/Runners"))
        lib_dir_raw = os.environ.get("LIB_DIR", "artifact/Cloud Bench")
        lib_dir = Path(lib_dir_raw) if lib_dir_raw else None
        if not runner_dir.is_dir():
            raise RuntimeError(f"Runner directory does not exist: {runner_dir}")
        if lib_dir is not None and not lib_dir.is_dir():
            lib_dir = None
        dest_prefix = f"projects/{project}"
        runner_binary = runner_dir / "cloud_bench_runner"
        _require_nonempty_file(runner_binary, label="cloud_bench_runner")
        local_files: list[dict[str, Any]] = [
            {
                "name": "cloud_bench_runner",
                "size": runner_binary.stat().st_size,
                "sha256": _sha256_file(runner_binary),
                "path": str(runner_binary),
                "dest": f"{bucket_root}/{dest_prefix}/cloud_bench_runner",
            },
        ]
        if lib_dir is not None:
            lib_file = lib_dir / "libCloud Bench.so"
            if lib_file.is_file():
                _require_nonempty_file(lib_file, label="libCloud Bench.so")
                local_files.append(
                    {
                        "name": "libCloud Bench.so",
                        "size": lib_file.stat().st_size,
                        "sha256": _sha256_file(lib_file),
                        "path": str(lib_file),
                        "dest": f"{bucket_root}/{dest_prefix}/libCloud Bench.so",
                    }
                )
        return local_files

    def _collect_bundle_upload_files(self, *, project: str, bucket_root: str) -> list[dict[str, Any]]:
        bundle_dir = Path(os.environ.get("RUNNER_BUNDLE_DIR", "artifact/runner-bundle"))
        if not bundle_dir.is_dir():
            raise RuntimeError(f"Runner bundle directory does not exist: {bundle_dir}")
        section = runner_publish_section(project)
        globs_raw = section.get("bundle_globs", ["cloud_bench_runner", "*.so", "*.so.*"])
        globs = [str(g) for g in globs_raw] if isinstance(globs_raw, list) else ["cloud_bench_runner", "*.so", "*.so.*"]
        paths = iter_bundle_files(bundle_dir, globs)
        if not paths:
            raise RuntimeError(f"No bundle files matched under {bundle_dir}")
        gate_prefix = gate_runner_prefix(project)
        local_files: list[dict[str, Any]] = []
        for path in paths:
            _require_nonempty_file(path, label=path.name)
            local_files.append(
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                    "path": str(path),
                    "dest": f"{bucket_root}/{gate_prefix}/{path.name}",
                }
            )
        return local_files

    def upload(self) -> None:
        self._cfg.require_gcp()
        bucket = self._cfg.gcs_bucket
        project = core.require_env("PROJECT")
        preset = core.require_env("PRESET")
        source_ref = os.environ.get("SOURCE_REF", "")
        root = core.bucket_root_uri(bucket)
        layout = runner_publish_layout(project)
        if layout == "bundle_directory":
            local_files = self._collect_bundle_upload_files(project=project, bucket_root=root)
            dest_prefix = gate_runner_prefix(project)
        else:
            local_files = self._collect_flat_upload_files(project=project, bucket_root=root)
            dest_prefix = f"projects/{project}"
        meta_dest = f"{root}/projects/{project}/runner_meta.json"
        remote_meta, _ = gcs.download_json(meta_dest)
        remote_files = {}
        if isinstance(remote_meta, dict) and isinstance(remote_meta.get("files"), list):
            for row in remote_meta["files"]:
                if isinstance(row, dict) and str(row.get("name", "")).strip():
                    remote_files[str(row["name"])] = row
        uploaded = []
        skipped = []
        for row in local_files:
            name = str(row["name"])
            local_size = int(row.get("size", 0) or 0)
            local_sha = str(row["sha256"])
            remote = remote_files.get(name, {})
            remote_size = (
                int(remote.get("size", -1))
                if isinstance(remote.get("size"), (int, str)) and str(remote.get("size")).isdigit()
                else -1
            )
            remote_sha = str(remote.get("sha256", "")).strip().lower()
            if remote_size == local_size and remote_sha == local_sha:
                skipped.append(name)
                continue
            local_path = Path(str(row["path"]))
            dest_uri = str(row["dest"])
            try:
                _upload_runner_file(local_path, dest_uri, executable=name == "cloud_bench_runner")
            except gcs.GcsError as exc:
                raise RuntimeError(f"Failed to upload {name}: {exc}") from exc
            uploaded.append({"name": name, "size": local_size, "sha256": local_sha})
            print(f"Uploaded {name} -> {row['dest']}")
        if not uploaded:
            print(
                f"Runner upload skipped: no content changes for {project}/{preset} ({', '.join(skipped) if skipped else 'none'})"
            )
            write_runner_provenance(bucket, root, dest_prefix, local_files, source_ref, project, preset)
            return
        build_ref = (os.environ.get("BUILD_REF") or "").strip()
        meta = {
            "uploaded_at": Instant.now().format_iso(unit="second"),
            "source_ref": source_ref,
            "project": project,
            "preset": preset,
            "runner_publish_layout": layout,
            "files": [
                {"name": str(r["name"]), "size": int(r["size"]), "sha256": str(r["sha256"])} for r in local_files
            ],
            "uploaded_files": uploaded,
            "skipped_unchanged_files": skipped,
        }
        if build_ref:
            meta["build_ref"] = build_ref
        try:
            gcs.upload_json(meta_dest, meta)
        except gcs.GcsError as exc:
            raise RuntimeError(f"Failed to upload runner_meta.json: {exc}") from exc
        print(f"Uploaded runner_meta.json -> {meta_dest}")
        write_runner_provenance(bucket, root, dest_prefix, local_files, source_ref, project, preset)
        print(f"Runner upload complete: {len(uploaded)} changed file(s) for {project}/{preset}")

    def upload_runner_to_gcs(self) -> None:
        project = os.environ.get("PROJECT", "").strip().lower()
        if runner_publish_layout(project) == "bundle_directory":
            runner = Path(os.environ.get("RUNNER_BUNDLE_DIR", "artifact/runner-bundle")) / "cloud_bench_runner"
        else:
            runner = Path(os.environ.get("RUNNER_DIR", "artifact/Runners")) / "cloud_bench_runner"
        if runner.is_file():
            with contextlib.suppress(OSError):
                runner.chmod(0o755)
        self.upload()

    def publish_release(self) -> None:
        """Upload tag-built runner to gate for one OEM (``runner publish-release``)."""
        self._cfg.require_gcp()
        project = core.require_env("GATE_PROJECT").strip().lower()
        core.require_env("PRESET")
        core.require_env("SOURCE_REF")
        if not (os.environ.get("BUILD_REF") or "").strip():
            os.environ["BUILD_REF"] = (os.environ.get("GIT_TAG") or os.environ.get("GITHUB_REF_NAME") or "").strip()
        os.environ.setdefault("PROJECT", project)
        if runner_publish_layout(project) == "bundle_directory":
            runner = Path(os.environ.get("RUNNER_BUNDLE_DIR", "artifact/runner-bundle")) / "cloud_bench_runner"
        else:
            runner = Path(os.environ.get("RUNNER_DIR", "artifact/Runners")) / "cloud_bench_runner"
        _require_nonempty_file(runner, label="cloud_bench_runner")
        if project == "lgtv":
            proc = subprocess.run(["strings", str(runner)], check=False, capture_output=True, text=True)
            if "Unknown LGVS_W car model" in (proc.stdout or ""):
                raise RuntimeError("Refusing LGVS_W runner for lgtv gate publish — build LGTV_gcc_Release")
        root = core.bucket_root_uri(self._cfg.gcs_bucket)
        gate_prefix = gate_runner_prefix(project)
        _rotate_gate_runner_prefix(root, gate_prefix)
        self.upload()

    def resolve_uploaded_projects(self) -> None:
        run_id = _ci_run_id_for_markers()
        root = core.workflow_runtime_root()
        prefix = f"{root}/_workflow/uploaded/{run_id}/"
        uris = gcs.list_prefix(prefix)
        uploaded_projects = {u.split("/")[-1].replace(".json", "").strip() for u in uris if u.endswith(".json")}
        w = self._w()
        runner_matrix_raw = read_workflow_str(w, "runner_matrix", "RUNNER_MATRIX")
        if runner_matrix_raw:
            try:
                runner_matrix = json.loads(runner_matrix_raw)
                include: list[object] = runner_matrix.get("include", []) if isinstance(runner_matrix, dict) else []
                if isinstance(include, list):
                    for entry in include:
                        if not isinstance(entry, dict):
                            continue
                        entry_d = cast(dict[str, object], entry)
                        project_raw = entry_d.get("project")
                        preset_raw = entry_d.get("preset")
                        project = str(project_raw).strip() if isinstance(project_raw, str) else ""
                        preset = str(preset_raw).strip() if isinstance(preset_raw, str) else ""
                        if not project or not preset:
                            continue
                        if _runner_meta_in_gcs(root, project, preset) is not None or _runner_binary_exists_in_gcs(
                            root, project, preset
                        ):
                            uploaded_projects.add(project)
            except json.JSONDecodeError as exc:
                gh_warning(f"Invalid RUNNER_MATRIX JSON; skipping GCS runner pre-scan: {exc}")
        names = sorted(uploaded_projects)
        accepted = json.dumps(names)
        Path("accepted.txt").write_text(accepted)
        write_github_output(os.environ.get("GITHUB_OUTPUT"), "accepted_projects", accepted)
        gh_notice(f"Runners uploaded for projects: {accepted}")

    def summarize_matrix_handshake(self) -> None:
        w = self._w()
        runner_matrix_raw = read_workflow_str(w, "runner_matrix", "RUNNER_MATRIX", "{}")
        filtered_raw = read_workflow_str(w, "filtered_matrix", "FILTERED_MATRIX", "{}")
        if not runner_matrix_raw or not filtered_raw:
            raise RuntimeError("RUNNER_MATRIX and FILTERED_MATRIX are required")
        json.loads(runner_matrix_raw)
        accepted_raw = read_workflow_str(w, "accepted", "ACCEPTED", "[]")
        accepted = json.loads(accepted_raw)
        filtered_matrix = json.loads(filtered_raw)
        bmt_jobs = sorted({str(e.get("project", "")).strip() for e in filtered_matrix.get("include", []) if e})
        print(f"::notice::Matrix handshake: uploaded={len(accepted)} legs={len(bmt_jobs)}")

    def filter_bmt_presets_upstream(self) -> None:
        """Emit ``matrix``, ``count``, ``has_presets`` to ``GITHUB_OUTPUT`` (core-main filter script parity)."""
        raw_root = (os.environ.get("FILTER_BMT_ARTIFACT_ROOT") or os.environ.get("BMT_ARTIFACT_ROOT") or "").strip()
        artifact_root = Path(raw_root or "upstream-artifacts").resolve()
        repo_root = Path(
            (os.environ.get("BMT_REPO_ROOT") or os.environ.get("GITHUB_WORKSPACE") or ".").strip() or "."
        ).resolve()
        out = core.require_env("GITHUB_OUTPUT")
        items, count, has_presets = filter_bmt_presets_upstream_artifacts_matrix(artifact_root, repo_root)
        matrix_payload = json.dumps(items, separators=(",", ":"))
        with Path(out).open("a", encoding="utf-8") as fh:
            fh.write(f"matrix={matrix_payload}\n")
            fh.write(f"count={count}\n")
            fh.write(f"has_presets={'true' if has_presets else 'false'}\n")
