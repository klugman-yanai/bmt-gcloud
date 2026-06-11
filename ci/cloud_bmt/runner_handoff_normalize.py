"""Normalize downloaded ``runner-*`` CI artifacts for ``runner upload-to-gcs``."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from cloud_bmt.runner_publish import iter_bundle_files, runner_publish_layout, runner_publish_section


def _find_runner_subdir(download_root: Path) -> Path:
    direct = download_root / "runner"
    if direct.is_dir() and (direct / "cloud_bench_runner").is_file():
        return direct
    for path in sorted(download_root.rglob("cloud_bench_runner")):
        if path.is_file():
            return path.parent
    raise RuntimeError(f"cloud_bench_runner not found under {download_root}")


def normalize_handoff_artifact() -> None:
    project = os.environ["PROJECT"].strip().lower()
    download = Path(os.environ.get("ARTIFACT_DOWNLOAD", "artifact-download")).resolve()
    layout = runner_publish_layout(project)

    if layout == "bundle_directory":
        src = _find_runner_subdir(download)
        dest = Path("artifact/runner-bundle").resolve()
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        globs = runner_publish_section(project).get("bundle_globs", ["cloud_bench_runner", "*.so", "*.so.*"])
        if not isinstance(globs, list):
            globs = ["cloud_bench_runner", "*.so", "*.so.*"]
        for path in iter_bundle_files(src, globs):
            shutil.copy2(path, dest / path.name)
        runner = dest / "cloud_bench_runner"
        if not runner.is_file():
            raise RuntimeError(f"bundle missing cloud_bench_runner after normalize ({dest})")
        runner.chmod(0o755)
        return

    runner_out = Path("artifact/Runners").resolve()
    lib_out = Path("artifact/Cloud Bench").resolve()
    runner_out.mkdir(parents=True, exist_ok=True)
    lib_out.mkdir(parents=True, exist_ok=True)
    src = _find_runner_subdir(download)
    shutil.copy2(src / "cloud_bench_runner", runner_out / "cloud_bench_runner")
    (runner_out / "cloud_bench_runner").chmod(0o755)
    lib = src / "libCloud Bench.so"
    if not lib.is_file():
        for candidate in src.glob("libCloud Bench.so*"):
            if candidate.is_file():
                lib = candidate
                break
    if lib.is_file():
        shutil.copy2(lib, lib_out / lib.name)
