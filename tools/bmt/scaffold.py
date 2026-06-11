"""Scaffold root-level Cloud BMT project sources."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from tools.bmt.project_bundle import BUNDLE_MANIFEST_NAME, load_project_bundle
from tools.bmt.project_sources import examples_source_dir
from tools.repo.paths import suite_root

_PROJECTS_DIRNAME = "projects"


def _validate_name(name: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
        raise ValueError(
            f"Invalid name: {name!r} — use lowercase letters, digits, hyphens, underscores; "
            "must start with a letter (e.g. skyworth, skyworth_tv)."
        )


def _source_root(source_root: Path | None) -> Path:
    return source_root if source_root is not None else suite_root()


def _project_dir(root: Path, project: str) -> Path:
    return root / _PROJECTS_DIRNAME / project


def _template_dir(root: Path) -> Path:
    candidate = examples_source_dir(root)
    if candidate.is_dir():
        return candidate
    repo_examples = suite_root() / "examples"
    if repo_examples.is_dir():
        return repo_examples
    return candidate


def _write_project_bundle(path: Path, project: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    data["project"] = project
    data["description"] = f"{project} Cloud BMT project"
    data.pop("plugin_runtime", None)
    data.pop("template", None)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _patch_scaffolded_tree(project_dir: Path, project: str) -> None:
    """Replace template slug / paths after copytree."""
    bmt_slug = "example_bmt"
    bundle_path = project_dir / BUNDLE_MANIFEST_NAME
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict):
        raise ValueError(f"Expected JSON object in {bundle_path}")
    bmts = bundle.get("bmts")
    if not isinstance(bmts, dict) or bmt_slug not in bmts or not isinstance(bmts[bmt_slug], dict):
        raise ValueError(f"Expected bmts.{bmt_slug} object in {bundle_path}")
    bmts[bmt_slug]["bmt_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://bmt/{project}/{bmt_slug}"))
    runner = bundle.get("runner")
    if isinstance(runner, dict):
        runner["uri"] = ""
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    plugin_py = project_dir / "plugin.py"
    if plugin_py.is_file():
        text = plugin_py.read_text(encoding="utf-8")
        plugin_py.write_text(text.replace('project="template"', f'project="{project}"'), encoding="utf-8")


def _strip_worker_scaffold(project_dir: Path) -> None:
    plugins_dir = project_dir / "plugins"
    if plugins_dir.is_dir():
        shutil.rmtree(plugins_dir)


def _bmt_manifest(project: str, bmt_slug: str) -> str:
    return (
        json.dumps(
            {
                "schema_version": 1,
                "project": project,
                "bmt_slug": bmt_slug,
                "bmt_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://bmt/{project}/{bmt_slug}")),
                "enabled": False,
                "inputs_prefix": f"projects/{project}/inputs/{bmt_slug}",
                "results_prefix": f"projects/{project}/results/{bmt_slug}",
                "outputs_prefix": f"projects/{project}/outputs/{bmt_slug}",
                "runner": {
                    "uri": "",
                    "deps_prefix": "",
                    "template_path": "runtime/assets/cloud_bench_input_template.json",
                },
                "plugin_config": {
                    "comparison": "gte",
                    "tolerance_abs": 0.25,
                    "reporting_hints": {
                        "metric_short_label": "example score",
                        "success_in_words": "Replace this with project-specific operator copy.",
                    },
                },
            },
            indent=2,
        )
        + "\n"
    )


def add_project(project: str, *, source_root: Path | None = None, dry_run: bool = False) -> int:
    """Copy the suite ``examples/`` scaffold to ``projects/<project>/`` at the suite root."""
    _validate_name(project)
    root = _source_root(source_root)
    target = _project_dir(root, project)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Project scaffold already exists: {target}")
    if dry_run:
        return 0

    template = _template_dir(root)
    if not template.is_dir():
        raise FileNotFoundError(f"Template project does not exist: {template}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, target)
    _write_project_bundle(target / BUNDLE_MANIFEST_NAME, project)
    _patch_scaffolded_tree(target, project)
    _strip_worker_scaffold(target)
    return 0


def add_bmt(
    project: str,
    bmt_slug: str,
    *,
    source_root: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Add a disabled BMT entry to ``projects/<project>/project.bmt.json``."""
    _validate_name(project)
    _validate_name(bmt_slug)
    root = _source_root(source_root)
    project_dir = _project_dir(root, project)
    if not project_dir.exists():
        raise FileNotFoundError(f"Project scaffold does not exist: {project_dir}")
    bundle_path = project_dir / BUNDLE_MANIFEST_NAME
    bundle = load_project_bundle(bundle_path)
    if bmt_slug in bundle.bmts:
        raise FileExistsError(f"BMT scaffold already exists: {bundle_path} bmts.{bmt_slug}")
    if not dry_run:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bmts = payload.setdefault("bmts", {})
        if not isinstance(bmts, dict):
            raise ValueError(f"Expected bmts object in {bundle_path}")
        entry = json.loads(_bmt_manifest(project, bmt_slug))
        plugin_config = entry.pop("plugin_config")
        for key in ("schema_version", "project", "bmt_slug", "inputs_prefix", "results_prefix", "outputs_prefix", "runner"):
            entry.pop(key, None)
        entry.update(plugin_config)
        bmts[bmt_slug] = entry
        bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0
