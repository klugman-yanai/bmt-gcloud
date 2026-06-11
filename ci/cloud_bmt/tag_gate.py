"""Map core-main git tags to gate projects (case-insensitive prefix)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from semver import Version

_TAG_GATE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "tag_to_gate.json"
_RELEASE_SUFFIX = re.compile(r"^v[0-9]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TagGateEntry:
    tag_prefix: str
    gate_project: str
    configure_preset: str
    build_preset: str
    bmt_key: str
    arch: str
    os_name: str


@dataclass(frozen=True, slots=True)
class TagResolveResult:
    tag: str
    tag_prefix: str
    version_suffix: str
    entry: TagGateEntry


def config_path() -> Path:
    return _TAG_GATE_CONFIG


@lru_cache(maxsize=1)
def load_tag_gate_entries() -> tuple[TagGateEntry, ...]:
    raw = json.loads(config_path().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{config_path()}: expected JSON object")
    rows = raw.get("entries")
    if not isinstance(rows, list):
        raise TypeError(f"{config_path()}: entries must be a list")
    out: list[TagGateEntry] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        prefix = str(row.get("tag_prefix", "")).strip().lower()
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        out.append(
            TagGateEntry(
                tag_prefix=prefix,
                gate_project=str(row.get("gate_project", "")).strip().lower(),
                configure_preset=str(row.get("configure_preset", "")).strip(),
                build_preset=str(row.get("build_preset", "")).strip(),
                bmt_key=str(row.get("bmt_key", "")).strip(),
                arch=str(row.get("arch", "x86_64")).strip(),
                os_name=str(row.get("os_name", "linux")).strip(),
            )
        )
    return tuple(out)


def _entries_by_prefix() -> dict[str, TagGateEntry]:
    return {e.tag_prefix: e for e in load_tag_gate_entries()}


def parse_release_tag(tag: str) -> tuple[str, str] | None:
    """Return ``(prefix_lower, version_suffix)`` when ``tag`` is a mapped release tag."""
    text = tag.strip()
    if "/" not in text:
        return None
    prefix_raw, suffix = text.split("/", 1)
    prefix = prefix_raw.strip().lower()
    version = suffix.strip()
    if not prefix or not version or not _RELEASE_SUFFIX.match(version):
        return None
    if prefix not in _entries_by_prefix():
        return None
    return prefix, version


def resolve_tag(tag: str) -> TagResolveResult | None:
    parsed = parse_release_tag(tag)
    if parsed is None:
        return None
    prefix, version = parsed
    entry = _entries_by_prefix()[prefix]
    return TagResolveResult(tag=tag.strip(), tag_prefix=prefix, version_suffix=version, entry=entry)


def _version_sort_key(version_suffix: str) -> tuple[int, ...] | None:
    text = version_suffix.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    parts: list[int] = []
    for piece in text.split("."):
        if not piece.isdigit():
            return None
        parts.append(int(piece))
    return tuple(parts) if parts else None


def tag_version_key(version_suffix: str) -> Version | None:
    """Parse ``v1.2.3`` for ordering; returns None when not semver-shaped."""
    text = version_suffix.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    pieces = text.split(".")
    if len(pieces) > 3:
        text = ".".join(pieces[:3])
    try:
        return Version.parse(text, optional_minor_and_patch=True)
    except ValueError:
        return None


def newest_release_tag_for_prefix(tags: list[str], tag_prefix: str) -> str | None:
    """Return the newest ``prefix/v*`` tag string among ``tags`` (case-insensitive prefix)."""
    want = tag_prefix.strip().lower()
    best_ver: tuple[int, ...] | None = None
    best_tag: str | None = None
    for tag in tags:
        parsed = parse_release_tag(tag)
        if parsed is None or parsed[0] != want:
            continue
        key = _version_sort_key(parsed[1])
        if key is None:
            continue
        if best_ver is None or key > best_ver:
            best_ver = key
            best_tag = tag.strip()
    return best_tag


def gate_entry_for_project(gate_project: str) -> TagGateEntry | None:
    slug = gate_project.strip().lower()
    for entry in load_tag_gate_entries():
        if entry.gate_project == slug:
            return entry
    return None


@lru_cache(maxsize=1)
def _preset_slug_to_gate_project() -> dict[str, str]:
    """Map CMake preset slug (``sei_robotics``) or ``bmt_key`` lower to gate bucket slug."""
    out: dict[str, str] = {}
    for entry in load_tag_gate_entries():
        slug = entry.configure_preset.removesuffix("_gcc_Release").lower()
        out[slug] = entry.gate_project
        out[entry.bmt_key.lower()] = entry.gate_project
        out[entry.bmt_key.lower().replace("_", "-")] = entry.gate_project
    return out


def gate_project_for_preset_slug(preset_slug: str) -> str:
    """Return gate bucket project for a release preset slug (e.g. ``sei_robotics`` → ``freebox``)."""
    key = preset_slug.strip().lower()
    return _preset_slug_to_gate_project().get(key, key)


def gate_project_for_bmt_key(bmt_key: str) -> str:
    """Return gate bucket project for a core-main matrix ``bmt_key`` (e.g. ``SEI_ROBOTICS`` → ``freebox``)."""
    return gate_project_for_preset_slug(bmt_key)


def write_github_outputs(result: TagResolveResult | None, *, github_output: str) -> None:
    """Emit resolve outputs for Actions (skip=true when unmapped)."""
    path = Path(github_output)
    lines: list[str]
    if result is None:
        lines = ["skip=true"]
    else:
        e = result.entry
        lines = [
            "skip=false",
            f"gate_project={e.gate_project}",
            f"configure_preset={e.configure_preset}",
            f"build_preset={e.build_preset}",
            f"bmt_key={e.bmt_key}",
            f"arch={e.arch}",
            f"os_name={e.os_name}",
            f"tag_prefix={result.tag_prefix}",
            f"build_ref={result.tag}",
            "runnable_on_bmt_runner=true",
        ]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
