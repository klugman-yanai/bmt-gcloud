"""Bootstrap flat runner binaries and metadata for a project in the BMT bucket."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from cloud_bmt import gcs
from cloud_bmt.runner_provenance import write_runner_provenance
from whenever import Instant

from tools.shared.bucket_env import bucket_root_uri


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_row(path: Path, name: str, dest: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{name} not found: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"{name} is empty: {path}")
    return {
        "name": name,
        "size": size,
        "sha256": _sha256_file(path),
        "path": str(path),
        "dest": dest,
    }


class BucketBootstrapRunnerMeta:
    """Seed projects/<project>/ runner files plus metadata without GitHub artifacts."""

    def run(
        self,
        *,
        bucket: str,
        project: str,
        preset: str,
        source_ref: str,
        binaries: Path | str,
    ) -> int:
        if not bucket:
            print("::error::Set GCS_BUCKET (or pass --bucket)", file=sys.stderr)
            return 1
        project = project.strip()
        preset = preset.strip()
        source_ref = source_ref.strip()
        if not project:
            print("::error::project is required", file=sys.stderr)
            return 1
        if not preset:
            print("::error::preset is required", file=sys.stderr)
            return 1
        if not source_ref:
            print("::error::source-ref is required", file=sys.stderr)
            return 1

        binaries_dir = Path(binaries)
        root = bucket_root_uri(bucket)
        dest_prefix = f"projects/{project}"
        local_files = [
            _file_row(
                binaries_dir / "cloud_bench_runner",
                "cloud_bench_runner",
                f"{root}/{dest_prefix}/cloud_bench_runner",
            ),
            _file_row(
                binaries_dir / "libCloud Bench.so",
                "libCloud Bench.so",
                f"{root}/{dest_prefix}/libCloud Bench.so",
            ),
        ]
        now = Instant.now().format_iso(unit="second")
        meta = {
            "uploaded_at": now,
            "source_ref": source_ref,
            "project": project,
            "preset": preset,
            "files": [
                {"name": str(row["name"]), "size": int(row["size"]), "sha256": str(row["sha256"])}
                for row in local_files
            ],
            "uploaded_files": [
                {"name": str(row["name"]), "size": int(row["size"]), "sha256": str(row["sha256"])}
                for row in local_files
            ],
            "skipped_unchanged_files": [],
        }
        latest_meta = {
            **meta,
            "uploaded_at_utc": now,
            "source": "bootstrap_runner_meta",
            "bucket_path": f"{root}/{dest_prefix}/cloud_bench_runner",
            "size_bytes": int(local_files[0]["size"]),
        }

        try:
            for row in local_files:
                gcs.write_object(str(row["dest"]), Path(str(row["path"])).read_bytes())
                print(f"Uploaded {row['name']} -> {row['dest']}")
            gcs.upload_json(f"{root}/{dest_prefix}/runner_meta.json", meta)
            gcs.upload_json(f"{root}/{dest_prefix}/runner_latest_meta.json", latest_meta)
            write_runner_provenance(bucket, root, dest_prefix, local_files, source_ref, project, preset)
        except (OSError, gcs.GcsError) as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1

        print(f"Bootstrapped runner metadata for {project}/{preset}")
        return 0
