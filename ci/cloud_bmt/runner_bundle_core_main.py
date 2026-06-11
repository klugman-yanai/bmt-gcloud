"""Stage core-main CI runner artifact dir + metadata.json for upload-artifact."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from cloud_bmt.preset import _binary_dir_for_configure, _load_presets
from cloud_bmt.runner_publish import runner_publish_layout_for_bmt_key
from cloud_bmt.runner_contracts import project_for_core_main_bmt_key


def _find_runner_binary(binary_dir: Path, *, max_depth: int = 3) -> Path | None:
    """Mirror ``find … -maxdepth 3`` matching ``cloud_bench_runner`` / ``cloud_bench_runner.exe``."""
    binary_dir = binary_dir.resolve()
    if not binary_dir.is_dir():
        return None
    names = {"cloud_bench_runner", "cloud_bench_runner.exe"}
    for dirpath, dirnames, filenames in os.walk(binary_dir, topdown=True):
        rel_s = os.path.relpath(dirpath, binary_dir)
        depth = 0 if rel_s in {".", ""} else len(Path(rel_s).parts)
        if depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            if fn in names:
                return Path(dirpath) / fn
    return None


def _copy_shared_libs(runner_path: Path, dest_dir: Path, binary_dir: Path) -> None:
    parent = runner_path.parent
    for pattern in ("*.so", "*.so.*"):
        for base in (parent, binary_dir / "Cloud Bench"):
            if not base.is_dir():
                continue
            for p in sorted(base.glob(pattern)):
                if p.is_file():
                    dest = dest_dir / p.name
                    if not dest.exists():
                        shutil.copy2(p, dest)


def bundle_core_main_artifact() -> None:
    """Env: ARTIFACT_ROOT, CONFIGURE_PRESET, BUILD_PRESET, BMT_KEY, ARCH, OS_NAME, RUNNABLE_ON_BMT_RUNNER.

    Optional: BMT_REPO_ROOT (default cwd), BMT_PRESETS_FILE (default CMakePresets.json).
    """
    artifact_root = Path(os.environ["ARTIFACT_ROOT"].strip()).resolve()
    configure = os.environ["CONFIGURE_PRESET"].strip()
    build_preset = os.environ["BUILD_PRESET"].strip()
    bmt_key = os.environ["BMT_KEY"].strip()
    arch = os.environ["ARCH"].strip()
    os_name = os.environ["OS_NAME"].strip()
    runnable_raw = os.environ["RUNNABLE_ON_BMT_RUNNER"].strip().lower()
    runnable_on_bmt_runner = runnable_raw in ("1", "true", "yes")

    repo_root = Path((os.environ.get("BMT_REPO_ROOT") or ".").strip() or ".").resolve()
    presets_path = Path(os.environ.get("BMT_PRESETS_FILE", "CMakePresets.json"))
    preset_file = presets_path if presets_path.is_absolute() else (repo_root / presets_path).resolve()

    presets = _load_presets(preset_file)
    binary_rel = Path(_binary_dir_for_configure(presets, configure))
    binary_dir = binary_rel if binary_rel.is_absolute() else (repo_root / binary_rel).resolve()

    bundle_root = artifact_root / "runner"
    bundle_root.mkdir(parents=True, exist_ok=True)

    runner_path = _find_runner_binary(binary_dir)
    if runner_path is None or not runner_path.is_file():
        raise RuntimeError(f"Expected runner binary was not produced for {build_preset}")

    shutil.copy2(runner_path, bundle_root / runner_path.name)
    _copy_shared_libs(runner_path, bundle_root, binary_dir)

    runner_name = runner_path.name
    project = project_for_core_main_bmt_key(bmt_key)
    bmt_supported = project is not None
    metadata = {
        "build_preset": build_preset,
        "configure_preset": configure,
        "bmt_key": bmt_key,
        "binary_dir": str(binary_dir),
        "runner_path": f"runner/{runner_name}",
        "arch": arch,
        "os": os_name,
        "runnable_on_bmt_runner": runnable_on_bmt_runner and bmt_supported,
        "bmt_supported": bmt_supported,
        "runner_publish_layout": runner_publish_layout_for_bmt_key(bmt_key),
        "project": project or "",
    }
    if not bmt_supported:
        metadata["skip_reason"] = "no suite BMT project mapping"
    (artifact_root / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
