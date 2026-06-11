"""Plugin dependency environment resolver for v2 worker plugins."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import venv
from pathlib import Path
from typing import Literal

from runtime.plugin_host.worker_protocol import WorkerRuntimeTarget

DependencyMode = Literal["none", "requirements", "pyproject"]


def _plugin_slug(target: WorkerRuntimeTarget) -> str:
    prefix = f"{target.project}."
    if target.plugin_id.startswith(prefix):
        return target.plugin_id[len(prefix) :]
    if "." in target.plugin_id:
        return target.plugin_id.rsplit(".", 1)[-1]
    return "default"


def _plugin_dir(project_dir: Path, target: WorkerRuntimeTarget) -> Path:
    return project_dir / "plugins" / _plugin_slug(target)


def _dependency_file(plugin_dir: Path) -> tuple[DependencyMode, Path | None]:
    requirements = plugin_dir / "requirements.txt"
    if requirements.is_file():
        return "requirements", requirements
    pyproject = plugin_dir / "pyproject.toml"
    if pyproject.is_file():
        return "pyproject", pyproject
    return "none", None


def _stage_root(project_dir: Path) -> Path:
    return project_dir.parents[1]


def _env_cache_dir(project_dir: Path) -> Path:
    return _stage_root(project_dir) / ".plugin-envs"


def _env_key(*, target: WorkerRuntimeTarget, mode: DependencyMode, dep_file: Path | None) -> str:
    digest = hashlib.sha256()
    digest.update(target.plugin_id.encode("utf-8"))
    digest.update(target.plugin_version.encode("utf-8"))
    digest.update(mode.encode("utf-8"))
    digest.update(f"{sys.version_info.major}.{sys.version_info.minor}".encode())
    if dep_file is not None:
        digest.update(dep_file.read_bytes())
    return digest.hexdigest()[:16]


def _site_packages(env_dir: Path) -> list[Path]:
    candidates = list(env_dir.glob("lib/python*/site-packages"))
    win_site = env_dir / "Lib" / "site-packages"
    if win_site.is_dir():
        candidates.append(win_site)
    return [path for path in candidates if path.is_dir()]


def _python_executable(env_dir: Path) -> Path:
    posix = env_dir / "bin" / "python"
    if posix.is_file():
        return posix
    win = env_dir / "Scripts" / "python.exe"
    if win.is_file():
        return win
    raise FileNotFoundError(f"Missing python executable in plugin env {env_dir}")


def _build_env(*, env_dir: Path, mode: DependencyMode, plugin_dir: Path, dep_file: Path | None) -> None:
    builder = venv.EnvBuilder(with_pip=True, clear=False, symlinks=True)
    builder.create(env_dir)
    python = _python_executable(env_dir)
    if mode == "requirements" and dep_file is not None:
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(dep_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    elif mode == "pyproject":
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(plugin_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def prepare_plugin_dependency_sys_paths(project_dir: Path, target: WorkerRuntimeTarget) -> list[Path]:
    """Return plugin dependency site-packages paths, building env lazily when needed."""

    plugin_dir = _plugin_dir(project_dir, target)
    mode, dep_file = _dependency_file(plugin_dir)
    if mode == "none":
        return []
    cache_dir = _env_cache_dir(project_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    env_dir = (
        cache_dir
        / f"{target.plugin_id.replace('.', '_')}_{target.plugin_version}_{_env_key(target=target, mode=mode, dep_file=dep_file)}"
    )
    if not env_dir.is_dir():
        _build_env(env_dir=env_dir, mode=mode, plugin_dir=plugin_dir, dep_file=dep_file)
    return _site_packages(env_dir)
