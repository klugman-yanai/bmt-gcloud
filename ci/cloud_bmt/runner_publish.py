"""Runner publish layout from ``projects/<slug>/project.bmt.json`` when present."""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal

from cloud_bmt.runner_contracts import contract_for_project, project_for_core_main_bmt_key

RunnerPublishLayout = Literal["flat_binary", "bundle_directory"]

_LAYOUT_DEFAULT: RunnerPublishLayout = "flat_binary"


def suite_root() -> Path:
    """Suite repo root (``cloud-bmt-suite``)."""
    return Path(__file__).resolve().parents[3]


def project_bundle_path(project: str) -> Path:
    return suite_root() / "projects" / project.strip().lower() / "project.bmt.json"


def oem_contract_path(project: str) -> Path:
    """Compatibility alias for callers that need the project contract source path."""
    return project_bundle_path(project)


def load_oem_contract(project: str) -> dict[str, Any] | None:
    path = project_bundle_path(project)
    if not path.is_file():
        return contract_for_project(project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path}: expected JSON object")
    contract = payload.get("oem_contract")
    if contract is None:
        return contract_for_project(project)
    if not isinstance(contract, dict):
        raise TypeError(f"{path}: expected oem_contract object")
    return contract


def runner_publish_section(project: str) -> dict[str, Any]:
    contract = load_oem_contract(project) or {}
    section = contract.get("runner_publish")
    return section if isinstance(section, dict) else {}


def runner_publish_layout(project: str) -> RunnerPublishLayout:
    raw = str(runner_publish_section(project).get("layout", _LAYOUT_DEFAULT)).strip()
    if raw == "bundle_directory":
        return "bundle_directory"
    if raw not in (_LAYOUT_DEFAULT, "bundle_directory"):
        raise ValueError(f"Unsupported runner_publish.layout for {project!r}: {raw!r}")
    return _LAYOUT_DEFAULT


def runner_publish_layout_for_bmt_key(bmt_key: str) -> RunnerPublishLayout:
    project = project_for_core_main_bmt_key(bmt_key)
    if not project:
        return _LAYOUT_DEFAULT
    return runner_publish_layout(project)


def gate_runner_prefix(project: str) -> str:
    section = runner_publish_section(project)
    explicit = str(section.get("gate_prefix", "")).strip()
    if explicit:
        return explicit.rstrip("/")
    if runner_publish_layout(project) == "bundle_directory":
        return f"projects/{project}/cloud_bench_runner"
    return f"projects/{project}"


def canonical_runner_object_uris(project: str, *, bucket_root: str) -> list[str]:
    """GCS object URIs that satisfy “runner present” for handoff preflight."""
    root = bucket_root.rstrip("/")
    layout = runner_publish_layout(project)
    prefix = gate_runner_prefix(project)
    if layout == "bundle_directory":
        return [f"{root}/{prefix}/cloud_bench_runner"]
    return [
        f"{root}/{prefix}/cloud_bench_runner",
        f"{root}/{project}/runners/{{preset}}/cloud_bench_runner",
    ]


def iter_bundle_files(bundle_dir: Path, globs: tuple[str, ...] | list[str]) -> list[Path]:
    bundle_dir = bundle_dir.resolve()
    if not bundle_dir.is_dir():
        return []
    patterns = tuple(globs) if globs else ("cloud_bench_runner", "*.so", "*.so.*")
    out: list[Path] = []
    for path in sorted(bundle_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if any(fnmatch(name, pat) for pat in patterns):
            out.append(path)
    return out
