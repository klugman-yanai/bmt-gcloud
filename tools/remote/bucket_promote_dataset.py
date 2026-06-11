"""Promote WAV datasets from krdm_bmt_per_project (or any GCS prefix) into the gate bucket."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.config.constants import DEFAULT_GCS_BUCKET
from tools.remote.gen_input_manifest import GenInputManifest
from tools.shared.bucket_env import bucket_from_env, bucket_root_uri
from tools.shared.gcloud_storage import GCloudStorageError, _gcloud_binary

DEFAULT_SOURCE_BUCKET = "krdm_bmt_per_project"

DEFAULT_RSYNC_EXCLUDES: tuple[str, ...] = (
    r".*/processed/.*",
    r".*\.txt$",
    r".*\.DS_Store$",
)

_PROFILES_PATH = Path(__file__).resolve().parents[2] / "ci" / "config" / "dataset_promotion_profiles.json"


@dataclass(frozen=True)
class PromotionProfile:
    name: str
    project: str
    dataset: str
    kind: str
    source_prefix: str
    skip_manifest: bool = False
    dest_prefix: str = ""


def normalize_gcs_prefix(uri: str) -> str:
    """Strip trailing slashes and generation suffixes from a gs:// prefix."""
    cleaned = uri.strip()
    if not cleaned.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {uri!r}")
    if "#" in cleaned:
        cleaned = cleaned[: cleaned.index("#")]
    return cleaned.rstrip("/")


def gate_dataset_uri(*, bucket: str, project: str, kind: str, dataset: str) -> str:
    segment = kind.strip().strip("/")
    if not segment or "/" in segment:
        raise ValueError(f"Invalid kind segment: {kind!r}")
    return f"{bucket_root_uri(bucket)}/projects/{project}/{segment}/{dataset}"


def build_source_prefix(
    *,
    source_bucket: str,
    source_prefix: str,
    smoke_prefix: str = "",
) -> str:
    base = normalize_gcs_prefix(f"{bucket_root_uri(source_bucket)}/{source_prefix.strip().lstrip('/')}")
    smoke = smoke_prefix.strip().strip("/")
    if smoke:
        return f"{base}/{smoke}"
    return base


def load_profiles_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _PROFILES_PATH
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {cfg_path}")
    return payload


def resolve_profile(name: str, *, config_path: Path | None = None) -> PromotionProfile:
    cfg = load_profiles_config(config_path)
    profiles = cfg.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("dataset_promotion_profiles.json missing profiles object")
    raw = profiles.get(name)
    if not isinstance(raw, dict):
        raise KeyError(f"Unknown promotion profile: {name}")

    project = str(raw["project"]).strip()
    dataset = str(raw["dataset"]).strip()
    kind = str(raw.get("kind", "inputs")).strip()
    skip_manifest = bool(raw.get("skip_manifest", False))

    if "source_prefix" in raw:
        source_prefix = str(raw["source_prefix"]).strip()
    else:
        folder = str(raw["source_folder"]).strip()
        leg = str(raw["raw_leg"]).strip()
        source_prefix = f"01_Projects/{folder}/raw_audio/{leg}"

    dest_prefix = str(raw.get("dest_prefix", "")).strip()

    return PromotionProfile(
        name=name,
        project=project,
        dataset=dataset,
        kind=kind,
        source_prefix=source_prefix,
        skip_manifest=skip_manifest,
        dest_prefix=dest_prefix,
    )


def list_oem_profile_names(project: str, *, config_path: Path | None = None) -> list[str]:
    cfg = load_profiles_config(config_path)
    oem_all = cfg.get("oem_all_legs")
    if not isinstance(oem_all, dict):
        raise ValueError("dataset_promotion_profiles.json missing oem_all_legs")
    names = oem_all.get(project)
    if not isinstance(names, list):
        raise KeyError(f"No oem_all_legs entry for project: {project}")
    return [str(n) for n in names]


def _gcloud_du_summary(uri: str) -> str:
    command = [_gcloud_binary(), "storage", "du", "-s", uri]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return f"(du failed: {(result.stderr or result.stdout).strip()})"
    return (result.stdout or "").strip().splitlines()[0] if result.stdout else "(empty)"


def rsync_gcs_prefix(
    *,
    source_uri: str,
    destination_uri: str,
    dry_run: bool = False,
    no_clobber: bool = True,
    excludes: tuple[str, ...] = DEFAULT_RSYNC_EXCLUDES,
) -> None:
    source = normalize_gcs_prefix(source_uri)
    dest = normalize_gcs_prefix(destination_uri)
    command = [
        _gcloud_binary(),
        "storage",
        "rsync",
        source,
        dest,
        "--recursive",
    ]
    if dry_run:
        command.append("--dry-run")
    if no_clobber:
        command.append("--no-clobber")
    for pattern in excludes:
        command.extend(["--exclude", pattern])
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise GCloudStorageError(f"rsync failed ({result.returncode}): {' '.join(command)}")


class BucketPromoteDataset:
    """GCS-to-GCS dataset promotion with optional manifest regeneration."""

    def run(
        self,
        *,
        project: str,
        dataset: str,
        source_bucket: str,
        source_prefix: str,
        dest_bucket: str | None = None,
        kind: str = "inputs",
        dry_run: bool = False,
        no_clobber: bool = True,
        smoke_prefix: str = "",
        gen_manifest: bool = True,
        skip_manifest: bool = False,
        dest_prefix: str = "",
        excludes: tuple[str, ...] = DEFAULT_RSYNC_EXCLUDES,
        stage_root: Path | str | None = None,
    ) -> int:
        if not project or not dataset:
            print("::error::project and dataset are required", file=sys.stderr)
            return 1
        if not source_prefix.strip():
            print("::error::source-prefix is required", file=sys.stderr)
            return 1

        dest = (dest_bucket or bucket_from_env() or DEFAULT_GCS_BUCKET).strip()
        if not dest:
            print("::error::Set GCS_BUCKET or pass --dest-bucket", file=sys.stderr)
            return 1

        src_uri = build_source_prefix(
            source_bucket=source_bucket,
            source_prefix=source_prefix,
            smoke_prefix=smoke_prefix,
        )
        custom_dest = dest_prefix.strip()
        dest_uri = (
            f"{bucket_root_uri(dest)}/{custom_dest.lstrip('/')}"
            if custom_dest
            else gate_dataset_uri(bucket=dest, project=project, kind=kind, dataset=dataset)
        )

        print(f"Source:      {src_uri}/")
        print(f"Destination: {dest_uri}/")
        print(f"Source size: {_gcloud_du_summary(src_uri)}")
        print(f"Dest before: {_gcloud_du_summary(dest_uri)}")

        try:
            rsync_gcs_prefix(
                source_uri=src_uri,
                destination_uri=dest_uri,
                dry_run=dry_run,
                no_clobber=no_clobber,
                excludes=excludes,
            )
        except GCloudStorageError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1

        if dry_run:
            print("(dry-run; skipped manifest generation)")
            return 0

        print(f"Dest after:  {_gcloud_du_summary(dest_uri)}")

        if skip_manifest or not gen_manifest:
            return 0

        from tools.repo.paths import DEFAULT_STAGE_ROOT

        stage = Path(stage_root) if stage_root else Path(DEFAULT_STAGE_ROOT)
        return GenInputManifest().run(
            bucket=dest,
            project=project,
            dataset=dataset,
            stage_inputs_segment=kind,
            stage_root=stage,
            dry_run=False,
            upload_to_gcs=True,
        )

    def run_profile(
        self,
        profile_name: str,
        *,
        source_bucket: str | None = None,
        dest_bucket: str | None = None,
        dry_run: bool = False,
        no_clobber: bool = True,
        smoke_prefix: str = "",
        gen_manifest: bool = True,
        config_path: Path | None = None,
        stage_root: Path | str | None = None,
    ) -> int:
        profile = resolve_profile(profile_name, config_path=config_path)
        cfg = load_profiles_config(config_path)
        default_src = str(cfg.get("default_source_bucket", DEFAULT_SOURCE_BUCKET))
        return self.run(
            project=profile.project,
            dataset=profile.dataset,
            source_bucket=(source_bucket or default_src).strip(),
            source_prefix=profile.source_prefix,
            dest_bucket=dest_bucket,
            kind=profile.kind,
            dry_run=dry_run,
            no_clobber=no_clobber,
            smoke_prefix=smoke_prefix,
            gen_manifest=gen_manifest,
            skip_manifest=profile.skip_manifest,
            dest_prefix=profile.dest_prefix,
            stage_root=stage_root,
        )

    def run_oem(
        self,
        project: str,
        *,
        source_bucket: str | None = None,
        dest_bucket: str | None = None,
        dry_run: bool = False,
        no_clobber: bool = True,
        smoke_prefix: str = "",
        config_path: Path | None = None,
        stage_root: Path | str | None = None,
    ) -> int:
        names = list_oem_profile_names(project, config_path=config_path)
        for name in names:
            print(f"\n=== profile {name} ===")
            rc = self.run_profile(
                name,
                source_bucket=source_bucket,
                dest_bucket=dest_bucket,
                dry_run=dry_run,
                no_clobber=no_clobber,
                smoke_prefix=smoke_prefix,
                config_path=config_path,
                stage_root=stage_root,
            )
            if rc != 0:
                return rc
        return 0
