"""Discover and build BmtPlugin instances from plugin.py."""

from __future__ import annotations

from types import ModuleType

from bmt_sdk.plugin import BmtPlugin

__all__ = ["load_plugin_from_module"]


def load_plugin_from_module(module: ModuleType) -> BmtPlugin:
    """Build a plugin from ``def plugin()``."""

    entrypoint = getattr(module, "plugin", None)
    if isinstance(entrypoint, BmtPlugin):
        return entrypoint
    if callable(entrypoint):
        loaded = entrypoint()
        if not isinstance(loaded, BmtPlugin):
            raise TypeError(f"plugin() must return BmtPlugin, got {type(loaded).__name__}")
        return loaded
    if entrypoint is not None:
        raise RuntimeError(f"plugin must be a BmtPlugin or callable returning BmtPlugin, got {type(entrypoint).__name__}")
    raise RuntimeError("plugin.py must define plugin() returning BmtPlugin")
