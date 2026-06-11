"""Worker protocol types for the plugin runtime host."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkerRuntimeTarget:
    """Resolved worker target identifier."""

    project: str
    plugin_id: str
    plugin_version: str
    entrypoint: str
