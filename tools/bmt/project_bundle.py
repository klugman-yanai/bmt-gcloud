"""Single-file authoring manifest for Cloud BMT projects."""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

BUNDLE_MANIFEST_NAME = "project.bmt.json"
PROJECT_MANIFEST_NAME = "project.json"

_BMT_MANIFEST_KEYS = {
    "schema_version",
    "project",
    "bmt_slug",
    "bmt_id",
    "enabled",
    "plugin_ref",
    "plugin_id",
    "plugin_version",
    "inputs_prefix",
    "results_prefix",
    "outputs_prefix",
    "runner",
    "execution",
    "plugin_config",
}


@dataclass(frozen=True, slots=True)
class ProjectBundle:
    project: dict[str, object]
    bmts: dict[str, dict[str, object]]


def _stable_bmt_id(project: str, bmt_slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://bmt/{project}/{bmt_slug}"))


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _int_value(value: object, default: int = 1) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | str):
        return int(value)
    return default


def _merge_mapping(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_mapping(
                cast(dict[str, object], existing),
                cast(dict[str, object], value),
            )
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_project_bundle(path: Path) -> ProjectBundle:
    data = _load_json_object(path)
    project = str(data.get("project", "")).strip()
    if not project:
        raise ValueError(f"Project bundle has no project name: {path}")

    project_manifest: dict[str, object] = {
        "schema_version": _int_value(data.get("schema_version", 1)),
        "project": project,
        "description": str(data.get("description", "")),
        "python_dependencies": list(data.get("python_dependencies", [])),
    }
    if data.get("template") is True:
        project_manifest["template"] = True

    runner_default = data.get("runner", {})
    if runner_default is not None and not isinstance(runner_default, dict):
        raise ValueError(f"Project bundle runner must be an object: {path}")
    defaults = data.get("defaults", {})
    if defaults is not None and not isinstance(defaults, dict):
        raise ValueError(f"Project bundle defaults must be an object: {path}")
    bmts_raw = data.get("bmts", {})
    if not isinstance(bmts_raw, dict) or not bmts_raw:
        raise ValueError(f"Project bundle must define at least one BMT under 'bmts': {path}")

    bmts: dict[str, dict[str, object]] = {}
    for bmt_slug, raw_bmt in bmts_raw.items():
        slug = str(bmt_slug).strip()
        if not slug:
            raise ValueError(f"Project bundle has an empty BMT slug: {path}")
        if not isinstance(raw_bmt, dict):
            raise ValueError(f"Project bundle BMT {slug!r} must be an object: {path}")
        merged = _merge_mapping(defaults, raw_bmt)
        plugin_config = {key: value for key, value in merged.items() if key not in _BMT_MANIFEST_KEYS}
        explicit_plugin_config = merged.get("plugin_config", {})
        if explicit_plugin_config is not None and not isinstance(explicit_plugin_config, dict):
            raise ValueError(f"Project bundle BMT {slug!r} plugin_config must be an object: {path}")
        if isinstance(explicit_plugin_config, dict):
            plugin_config.update(cast(dict[str, object], copy.deepcopy(explicit_plugin_config)))

        bmt: dict[str, object] = {
            key: copy.deepcopy(value)
            for key, value in merged.items()
            if key in _BMT_MANIFEST_KEYS and key != "plugin_config"
        }
        bmt["schema_version"] = _int_value(bmt.get("schema_version", data.get("schema_version", 1)))
        bmt["project"] = project
        bmt["bmt_slug"] = slug
        bmt["bmt_id"] = str(bmt.get("bmt_id") or _stable_bmt_id(project, slug))
        bmt["enabled"] = bool(bmt.get("enabled", False))
        bmt["inputs_prefix"] = str(bmt.get("inputs_prefix") or f"projects/{project}/inputs/{slug}")
        bmt["results_prefix"] = str(bmt.get("results_prefix") or f"projects/{project}/results/{slug}")
        bmt["outputs_prefix"] = str(bmt.get("outputs_prefix") or f"projects/{project}/outputs/{slug}")
        if runner_default and "runner" not in bmt:
            bmt["runner"] = copy.deepcopy(runner_default)
        bmt["plugin_config"] = plugin_config
        bmts[slug] = bmt
    return ProjectBundle(project=project_manifest, bmts=bmts)


def expand_project_bundle(project_dir: Path) -> bool:
    bundle_path = project_dir / BUNDLE_MANIFEST_NAME
    if not bundle_path.is_file():
        return False
    bundle = load_project_bundle(bundle_path)
    (project_dir / PROJECT_MANIFEST_NAME).write_text(
        json.dumps(bundle.project, indent=2) + "\n",
        encoding="utf-8",
    )
    for bmt_slug, bmt in bundle.bmts.items():
        (project_dir / f"{bmt_slug}.json").write_text(json.dumps(bmt, indent=2) + "\n", encoding="utf-8")
    bundle_path.unlink()
    return True
