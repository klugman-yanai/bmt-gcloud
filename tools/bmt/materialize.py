"""Materialize root Cloud BMT project folders into the runtime stage tree."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from tools.bmt.project_bundle import expand_project_bundle
from tools.bmt.project_sources import discover_project_sources, project_slug
from tools.repo.paths import DEFAULT_STAGE_ROOT, repo_root

_SKIP_DIRS = {
    ".git",
    ".local",
    "__pycache__",
    "outputs",
    "results",
    "plugin_workspaces",
}
_SKIP_SUFFIXES = {
    ".7z",
    ".dat",
    ".h5",
    ".onnx",
    ".parquet",
    ".pyc",
    ".snsr",
    ".so",
    ".tar",
    ".tar.gz",
    ".tflite",
    ".bin",
    ".wav",
    ".flac",
    ".mp3",
    ".pcm",
    ".xlsx",
    ".zip",
}
_SKIP_NAMES = {
    "cloud_bench_runner",
    "libCloud Bench.so",
}


@dataclass(frozen=True, slots=True)
class MaterializedProject:
    source_dir: Path
    project: str
    target_dir: Path


def _load_registry_yaml(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        payload = yaml.safe_load(text)
    except ModuleNotFoundError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Plugin registry must be a mapping object: {path}")
    return payload


def _write_plugin_index(project_target_dir: Path) -> None:
    """Write plugin-index.json only when an explicit worker registry exists."""

    registry_path = project_target_dir / "plugins" / "registry.yaml"
    if not registry_path.is_file():
        legacy_index = project_target_dir / "plugin-index.json"
        if legacy_index.is_file():
            legacy_index.unlink()
        return
    payload = _load_registry_yaml(registry_path)
    plugins = payload.get("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError(f"Plugin registry 'plugins' must be a list: {registry_path}")
    if not plugins:
        return
    index_path = project_target_dir / "plugin-index.json"
    index_path.write_text(json.dumps({"plugins": plugins}, indent=2, sort_keys=True), encoding="utf-8")


def _ignore(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(name)
        if name in _SKIP_NAMES or name in _SKIP_DIRS:
            ignored.add(name)
            continue
        if ".so." in name or any(name.endswith(suffix) for suffix in _SKIP_SUFFIXES):
            ignored.add(name)
            continue
        if path.suffix in _SKIP_SUFFIXES:
            ignored.add(name)
    return ignored


def materialize_projects(
    *,
    source_root: Path | None = None,
    stage_root: Path | None = None,
    clean: bool = True,
) -> list[MaterializedProject]:
    """Copy root project sources into ``stage_root/projects/<project>``."""
    stage = stage_root or (repo_root() / DEFAULT_STAGE_ROOT)
    projects_root = stage / "projects"
    sources = discover_project_sources(source_root)
    if clean and projects_root.exists():
        shutil.rmtree(projects_root)
    projects_root.mkdir(parents=True, exist_ok=True)

    materialized: list[MaterializedProject] = []
    for source_dir in sources:
        project = project_slug(source_dir)
        target_dir = projects_root / project
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir, ignore=_ignore)
        expand_project_bundle(target_dir)
        _write_plugin_index(target_dir)
        materialized.append(MaterializedProject(source_dir=source_dir, project=project, target_dir=target_dir))
    return materialized
