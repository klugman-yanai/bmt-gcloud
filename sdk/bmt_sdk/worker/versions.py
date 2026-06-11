"""Version negotiation helpers for the plugin worker ABI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedApiVersion:
    major: int
    minor: int

    @classmethod
    def parse(cls, raw: str) -> ParsedApiVersion:
        text = str(raw).strip()
        parts = text.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid plugin_api_version {raw!r}; expected '<major>.<minor>'")
        try:
            major = int(parts[0])
            minor = int(parts[1])
        except ValueError as exc:
            raise ValueError(f"Invalid plugin_api_version {raw!r}; expected numeric parts") from exc
        if major < 0 or minor < 0:
            raise ValueError(f"Invalid plugin_api_version {raw!r}; values must be non-negative")
        return cls(major=major, minor=minor)


class AbiIncompatibleError(RuntimeError):
    """Raised when runtime and plugin API versions are incompatible."""


def ensure_abi_compatible(*, runtime_api_version: str, plugin_api_version: str) -> None:
    """Enforce strict major compatibility and bounded minor compatibility."""

    runtime = ParsedApiVersion.parse(runtime_api_version)
    plugin = ParsedApiVersion.parse(plugin_api_version)
    if runtime.major != plugin.major:
        raise AbiIncompatibleError(
            f"Incompatible plugin API major: runtime={runtime_api_version} plugin={plugin_api_version}"
        )
    if plugin.minor > runtime.minor:
        raise AbiIncompatibleError(
            f"Plugin API minor is newer than runtime: runtime={runtime_api_version} plugin={plugin_api_version}"
        )
