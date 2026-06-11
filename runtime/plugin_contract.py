"""Author-facing plugin identity defaults."""

from __future__ import annotations

from typing import Any

DEFAULT_PLUGIN_PACKAGE = "default"
DEFAULT_PLUGIN_VERSION = "2.0.0"


def default_plugin_id(project: str, *, package: str = DEFAULT_PLUGIN_PACKAGE) -> str:
    return f"{project}.{package}"


def resolve_plugin_id(project: str, plugin_id: str | None = None) -> str:
    candidate = (plugin_id or "").strip()
    return candidate or default_plugin_id(project)


def resolve_plugin_version(plugin_version: str | None = None) -> str:
    candidate = (plugin_version or "").strip()
    return candidate or DEFAULT_PLUGIN_VERSION


def apply_bmt_manifest_defaults(
    data: dict[str, Any],
    *,
    project: str,
    bmt_slug: str,
) -> dict[str, Any]:
    """Fill platform-owned BMT manifest fields omitted from author JSON."""
    data.setdefault("schema_version", 1)
    data.setdefault("project", project)
    data.setdefault("bmt_slug", bmt_slug)
    data.setdefault("plugin_id", default_plugin_id(project))
    data.setdefault("plugin_version", DEFAULT_PLUGIN_VERSION)
    data.setdefault("inputs_prefix", f"projects/{project}/inputs/{bmt_slug}")
    data.setdefault("results_prefix", f"projects/{project}/results/{bmt_slug}")
    data.setdefault("outputs_prefix", f"projects/{project}/outputs/{bmt_slug}")
    return data
