"""Resolve Cloud Run task profile (standard vs heavy) from plugin declarations."""

from __future__ import annotations

from bmt_sdk.cloud_task_spec import CloudTaskProfile
from bmt_sdk.plugin import BmtPlugin


def normalize_cloud_task_profile(raw: str, *, context: str) -> CloudTaskProfile:
    profile = (raw or CloudTaskProfile.STANDARD.value).strip().lower()
    try:
        resolved = CloudTaskProfile(profile)
    except ValueError as exc:
        raise ValueError(f"{context}: cloud task profile must be 'standard' or 'heavy', got {raw!r}") from exc
    return resolved


def cloud_task_profile_from_plugin(
    plugin: BmtPlugin | None,
    *,
    bmt_slug: str,
) -> CloudTaskProfile | None:
    """Return the profile declared on the plugin instance, or ``None`` if unset."""
    if plugin is None:
        return None
    return plugin.cloud_task.for_slug(bmt_slug)


def resolve_cloud_task_profile(
    *,
    plugin: BmtPlugin | None,
    bmt_slug: str,
    manifest_profile: str,
) -> CloudTaskProfile:
    """Plugin declaration wins; manifest ``execution.profile`` is the fallback."""
    if plugin is not None:
        from_plugin = cloud_task_profile_from_plugin(plugin, bmt_slug=bmt_slug)
        if from_plugin is not None:
            return from_plugin
    return normalize_cloud_task_profile(manifest_profile, context="manifest execution.profile")
