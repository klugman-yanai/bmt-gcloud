"""Scaffold worker plugin packages inside a project source tree."""

from __future__ import annotations

import json
from pathlib import Path

from bmt_sdk.worker import PluginDescriptor

from tools.bmt.scaffold import _project_dir, _source_root, _validate_name

type RegistryPayload = dict[str, list[dict[str, object]]]


def _registry_path(project_dir: Path) -> Path:
    return project_dir / "plugins" / "registry.yaml"


def _load_registry(path: Path) -> RegistryPayload:
    if not path.is_file():
        return {"plugins": []}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        payload = yaml.safe_load(text)
    except ModuleNotFoundError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Registry file must be an object: {path}")
    plugins = payload.get("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError(f"Registry 'plugins' must be a list: {path}")
    typed_plugins = [dict(item) for item in plugins if isinstance(item, dict)]
    return {"plugins": typed_plugins}


def _save_registry(path: Path, payload: RegistryPayload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(serialized.rstrip() + "\n", encoding="utf-8")


def _worker_source(project: str, plugin_slug: str) -> str:
    plugin_id = f"{project}.{plugin_slug}"
    return f'''"""Worker plugin for {plugin_id}."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bmt_sdk import BmtPlugin
from bmt_sdk.context import ExecutionContext
from bmt_sdk.results import PreparedAssets
from bmt_sdk.worker import (
    EvaluateRequest,
    EvaluateResponse,
    ExecuteRequest,
    ExecuteResponse,
    PluginCapabilities,
    PluginDescriptor,
    PluginWorker,
    PrepareRequest,
    PrepareResponse,
    ScoreRequest,
    ScoreResponse,
)


class Worker(PluginWorker):
    def __init__(self) -> None:
        self._plugin = _load_project_plugin()

    def describe(self) -> PluginDescriptor:
        return PluginDescriptor(
            plugin_id="{plugin_id}",
            plugin_slug="{plugin_slug}",
            project="{project}",
            plugin_version="2.0.0",
            plugin_api_version="2.0",
            entrypoint="{project}_{plugin_slug}.worker:Worker",
            capabilities=PluginCapabilities(network_profile="none"),
        )

    def prepare(self, request: PrepareRequest) -> PrepareResponse:
        context = _context(request)
        prepared = self._plugin.prepare(context)
        return PrepareResponse(prepared_assets_extra=dict(prepared.extra))

    def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        context = _context(request)
        prepared = _prepared_assets_from_request(request)
        result = self._plugin.execute(context, prepared)
        return ExecuteResponse(execution_result=result)

    def score(self, request: ScoreRequest) -> ScoreResponse:
        context = _context(request)
        score = self._plugin.score(request.execution_result, request.baseline, context)
        return ScoreResponse(score_result=score)

    def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        context = _context(request)
        verdict = self._plugin.evaluate(request.score_result, request.baseline, context)
        return EvaluateResponse(verdict_result=verdict)


def _context(request: PrepareRequest | ExecuteRequest | ScoreRequest | EvaluateRequest) -> ExecutionContext:
    from bmt_sdk.models import BmtManifestView, ExecutionConfigView, ProjectManifestView, RunnerConfigView

    envelope = request.context
    manifest = BmtManifestView(
        project=request.plugin.project,
        bmt_slug=envelope.bmt_slug,
        bmt_id=envelope.bmt_id,
        enabled=True,
        plugin_config=dict(envelope.plugin_config),
        inputs_prefix="",
        results_prefix="",
        outputs_prefix="",
        execution=ExecutionConfigView(policy=envelope.execution_policy, profile=envelope.execution_profile),
        runner=RunnerConfigView(uri="", deps_prefix="", template_path=envelope.runner_template_path),
    )
    return ExecutionContext(
        project_manifest=ProjectManifestView(project=request.plugin.project, description=envelope.project_description),
        bmt_manifest=manifest,
        plugin_root=envelope.plugin_root,
        workspace_root=envelope.workspace_root,
        dataset_root=envelope.dataset_root,
        outputs_root=envelope.outputs_root,
        logs_root=envelope.logs_root,
        runner_path=envelope.runner_path,
        deps_root=envelope.deps_root,
    )


def _prepared_assets_from_request(request: ExecuteRequest) -> PreparedAssets:
    envelope = request.context
    return PreparedAssets(
        dataset_root=envelope.dataset_root,
        workspace_root=envelope.workspace_root,
        runner_path=envelope.runner_path,
        extra=dict(request.prepared_assets_extra),
    )


def _load_project_plugin() -> BmtPlugin:
    plugin_py = Path(__file__).resolve().parents[4] / "plugin.py"
    module_name = f"bmt_project_plugin_{{plugin_py.parent.name}}_{{id(plugin_py)}}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not create module spec for {{plugin_py}}")
    module = importlib.util.module_from_spec(spec)
    path_str = str(plugin_py.parent)
    added = path_str not in sys.path
    if added:
        sys.path.insert(0, path_str)
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        if added and path_str in sys.path:
            sys.path.remove(path_str)
    from bmt_sdk.discovery import load_plugin_from_module

    return load_plugin_from_module(module)
'''


def add_plugin_package(
    project: str, plugin_slug: str, *, source_root: Path | None = None, dry_run: bool = False
) -> int:
    _validate_name(project)
    _validate_name(plugin_slug)
    root = _source_root(source_root)
    project_dir = _project_dir(root, project)
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project scaffold does not exist: {project_dir}")
    package_name = f"{project}_{plugin_slug}"
    plugin_dir = project_dir / "plugins" / plugin_slug
    src_dir = plugin_dir / "src" / package_name
    plugin_toml = plugin_dir / "plugin.toml"
    registry_path = _registry_path(project_dir)
    registry = _load_registry(registry_path)
    plugin_id = f"{project}.{plugin_slug}"
    existing = [item for item in registry["plugins"] if item.get("plugin_id") == plugin_id]
    if existing:
        raise FileExistsError(f"Plugin {plugin_id} already exists in registry {registry_path}")
    descriptor = PluginDescriptor(
        plugin_id=plugin_id,
        plugin_slug=plugin_slug,
        project=project,
        plugin_version="2.0.0",
        plugin_api_version="2.0",
        entrypoint=f"{package_name}.worker:Worker",
    )
    if dry_run:
        return 0
    src_dir.mkdir(parents=True, exist_ok=False)
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    (src_dir / "worker.py").write_text(_worker_source(project, plugin_slug), encoding="utf-8")
    plugin_toml.write_text(
        "\n".join(
            [
                "[plugin]",
                f'id = "{plugin_id}"',
                f'slug = "{plugin_slug}"',
                'version = "2.0.0"',
                'api_version = "2.0"',
                f'entrypoint = "{package_name}.worker:Worker"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    plugins = list(registry["plugins"])
    plugins.append(descriptor.model_dump(mode="python"))
    _save_registry(registry_path, {"plugins": plugins})
    return 0
