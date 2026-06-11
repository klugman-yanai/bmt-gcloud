"""Validate plugin registry and descriptors for a project."""

from __future__ import annotations

from pathlib import Path

from bmt_sdk.worker import PluginDescriptor

from tools.bmt.plugin_package_scaffold import _load_registry
from tools.bmt.scaffold import _project_dir, _source_root, _validate_name


def validate_plugin_registry(project: str, *, source_root: Path | None = None) -> int:
    _validate_name(project)
    root = _source_root(source_root)
    project_dir = _project_dir(root, project)
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project scaffold does not exist: {project_dir}")
    registry_path = project_dir / "plugins" / "registry.yaml"
    payload = _load_registry(registry_path)
    plugins = payload.get("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError(f"Registry 'plugins' must be a list: {registry_path}")
    seen_ids: set[str] = set()
    for plugin in plugins:
        descriptor = PluginDescriptor.model_validate(plugin)
        if descriptor.project != project:
            raise ValueError(
                f"Registry plugin project mismatch: {descriptor.plugin_id} has project={descriptor.project!r}, expected {project!r}"
            )
        if descriptor.plugin_id in seen_ids:
            raise ValueError(f"Duplicate plugin_id in registry: {descriptor.plugin_id}")
        seen_ids.add(descriptor.plugin_id)
    return 0
