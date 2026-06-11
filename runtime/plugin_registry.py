"""Resolve worker plugins from stage materialized plugin indexes."""

from __future__ import annotations

import json
from pathlib import Path

from bmt_sdk.worker import PluginDescriptor, ensure_abi_compatible

_RUNTIME_PLUGIN_API_VERSION = "2.0"


def _index_path(stage_root: Path, project: str) -> Path:
    return stage_root / "projects" / project / "plugin-index.json"


def load_stage_plugin_index(*, stage_root: Path, project: str) -> list[PluginDescriptor]:
    path = _index_path(stage_root, project)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Plugin index must be an object: {path}")
    raw_plugins = payload.get("plugins", [])
    if not isinstance(raw_plugins, list):
        raise TypeError(f"Plugin index 'plugins' must be a list: {path}")
    return [PluginDescriptor.model_validate(item) for item in raw_plugins]


def resolve_plugin_descriptor(
    *,
    stage_root: Path,
    project: str,
    plugin_id: str,
    plugin_version: str,
) -> PluginDescriptor:
    descriptors = load_stage_plugin_index(stage_root=stage_root, project=project)
    for descriptor in descriptors:
        if descriptor.plugin_id == plugin_id and descriptor.plugin_version == plugin_version:
            ensure_abi_compatible(
                runtime_api_version=_RUNTIME_PLUGIN_API_VERSION,
                plugin_api_version=descriptor.plugin_api_version,
            )
            return descriptor
    raise ValueError(
        f"Plugin {plugin_id}@{plugin_version} was not found in {_index_path(stage_root, project)} for project {project}"
    )
