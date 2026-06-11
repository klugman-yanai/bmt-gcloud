from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.plugin_host import deps_env
from runtime.plugin_host.worker_protocol import WorkerRuntimeTarget


def _target() -> WorkerRuntimeTarget:
    return WorkerRuntimeTarget(
        project="acme",
        plugin_id="acme.default",
        plugin_version="2.0.0",
        entrypoint="acme_default.worker:Worker",
    )


def _write_requirements_plugin(project_dir: Path) -> Path:
    plugin_dir = project_dir / "plugins" / "default"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    return plugin_dir


def _write_pyproject_plugin(project_dir: Path) -> Path:
    plugin_dir = project_dir / "plugins" / "default"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "pyproject.toml").write_text("[project]\nname='acme-default'\nversion='0.1.0'\n", encoding="utf-8")
    return plugin_dir


def test_prepare_plugin_dependency_sys_paths_uses_requirements_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "stage" / "projects" / "acme"
    _write_requirements_plugin(project_dir)
    calls: list[list[str]] = []

    def fake_create(self, env_dir: Path) -> None:
        del self
        (Path(env_dir) / "bin").mkdir(parents=True, exist_ok=True)
        (Path(env_dir) / "bin" / "python").write_text("", encoding="utf-8")
        (Path(env_dir) / "lib" / "python3.12" / "site-packages").mkdir(parents=True, exist_ok=True)

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deps_env.venv.EnvBuilder, "create", fake_create)
    monkeypatch.setattr(deps_env.subprocess, "run", fake_run)

    paths_first = deps_env.prepare_plugin_dependency_sys_paths(project_dir, _target())
    paths_second = deps_env.prepare_plugin_dependency_sys_paths(project_dir, _target())
    assert paths_first
    assert paths_second == paths_first
    assert len(calls) == 1
    assert "-r" in calls[0]


def test_prepare_plugin_dependency_sys_paths_uses_pyproject_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "stage" / "projects" / "acme"
    plugin_dir = _write_pyproject_plugin(project_dir)
    calls: list[list[str]] = []

    def fake_create(self, env_dir: Path) -> None:
        del self
        (Path(env_dir) / "bin").mkdir(parents=True, exist_ok=True)
        (Path(env_dir) / "bin" / "python").write_text("", encoding="utf-8")
        (Path(env_dir) / "lib" / "python3.12" / "site-packages").mkdir(parents=True, exist_ok=True)

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deps_env.venv.EnvBuilder, "create", fake_create)
    monkeypatch.setattr(deps_env.subprocess, "run", fake_run)

    deps_env.prepare_plugin_dependency_sys_paths(project_dir, _target())
    assert len(calls) == 1
    assert calls[0][-1] == str(plugin_dir)
