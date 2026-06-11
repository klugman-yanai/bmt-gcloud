"""Suite-owned core-main runner contracts packaged with the BMT PEX."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

_PACKAGED_CONTRACTS = "resources/core_main_runner_projects.json"
_GCC_RELEASE_SUFFIX = "_gcc_Release"


def _suite_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalize_key(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _cmake_preset_slug(cmake_preset: object) -> str:
    raw = str(cmake_preset or "").strip()
    return _normalize_key(raw.removesuffix(_GCC_RELEASE_SUFFIX))


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path}: expected JSON object")
    return payload


def _local_project_contracts() -> dict[str, dict[str, Any]]:
    projects_root = _suite_root() / "projects"
    if not projects_root.is_dir():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(projects_root.glob("*/project.bmt.json")):
        payload = _load_json_file(path)
        if not payload:
            continue
        contract = payload.get("oem_contract")
        if not isinstance(contract, dict):
            continue
        project = str(contract.get("project") or payload.get("project") or path.parent.name).strip().lower()
        runner = contract.get("runner")
        if not project or not isinstance(runner, dict) or not str(runner.get("core_main_bmt_key", "")).strip():
            continue
        out[project] = contract
    return out


def _packaged_project_contracts() -> dict[str, dict[str, Any]]:
    data = resources.files("cloud_bmt").joinpath(_PACKAGED_CONTRACTS)
    payload = json.loads(data.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{_PACKAGED_CONTRACTS}: expected JSON object")
    projects = payload.get("projects")
    if not isinstance(projects, list):
        raise TypeError(f"{_PACKAGED_CONTRACTS}: projects must be a list")
    out: dict[str, dict[str, Any]] = {}
    for item in projects:
        if not isinstance(item, dict):
            continue
        project = str(item.get("project", "")).strip().lower()
        if project:
            out[project] = item
    return out


@lru_cache(maxsize=1)
def project_contracts() -> dict[str, dict[str, Any]]:
    contracts = _packaged_project_contracts()
    contracts.update(_local_project_contracts())
    return contracts


def contract_for_project(project: str) -> dict[str, Any] | None:
    return project_contracts().get(str(project).strip().lower())


def project_for_core_main_bmt_key(bmt_key: str) -> str | None:
    key = _normalize_key(bmt_key)
    if not key:
        return None
    for project, contract in project_contracts().items():
        runner = contract.get("runner")
        if not isinstance(runner, dict):
            continue
        candidates = {
            _normalize_key(project),
            _normalize_key(runner.get("core_main_bmt_key")),
            _cmake_preset_slug(runner.get("cmake_preset")),
        }
        if key in candidates:
            return project
    return None


def project_for_core_main_preset_slug(preset_slug: str) -> str | None:
    return project_for_core_main_bmt_key(preset_slug)
