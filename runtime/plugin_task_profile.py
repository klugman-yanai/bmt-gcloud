"""Load staged OEM ``plugin.py`` and resolve Cloud Run task profiles at plan time."""

from __future__ import annotations

from pathlib import Path

from bmt_sdk.cloud_task import resolve_cloud_task_profile

from runtime.plugin_loader import load_plugin_direct


def resolve_leg_execution_profile(
    *,
    stage_root: Path,
    project: str,
    bmt_slug: str,
    manifest_profile: str,
) -> str:
    """Return ``standard`` or ``heavy`` for workflow task routing."""
    project_dir = stage_root / "projects" / project
    plugin = None
    try:
        plugin, _ = load_plugin_direct(project_dir)
    except FileNotFoundError:
        plugin = None
    return resolve_cloud_task_profile(
        plugin=plugin,
        bmt_slug=bmt_slug,
        manifest_profile=manifest_profile,
    )
