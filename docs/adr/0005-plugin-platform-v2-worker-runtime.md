# ADR 0005: Worker-isolated plugin runtime

## Status

**Superseded in runtime behavior** by [ADR 0009](0009-direct-plugin-execution-default.md). This ADR remains as historical design context for worker packaging/tooling surfaces.

## Context

This ADR described a worker-isolated execution path resolved from
`projects/<slug>/plugins/registry.yaml` (materialized to `plugin-index.json` on the stage tree).
Current runtime execution starts from `projects/<slug>/plugin.py`; worker package artifacts remain
available for scaffolding and packaging workflows.

## Decision

1. **Worker package path (historical):** plugin IDs resolve via
   `runtime/plugin_registry.py` → `runtime/plugin_host/worker_client.py` for worker tooling flows.
2. **SDK surface:** typed contracts live in `bmt_sdk.worker` (`PluginDescriptor`,
   `PluginInvocation`, `PluginWorker`, hook request/response models).
3. **ABI:** `plugin_api_version` on each descriptor is negotiated via `ensure_abi_compatible`.
4. **Authoring:** `projects/<slug>/plugin.py` holds project settings and scoring policy; worker
   packages under `projects/<slug>/plugins/<slug>/` wrap that plugin for hook execution.

## Consequences

- Cloud Run runtime does not switch entrypoints based on worker metadata; execution starts at `plugin.py`.
- New plugins use `uv run python -m tools bmt add-plugin-package <project> <slug>` and
  `validate-plugin-registry`.
- Plugin dependency conflicts are reduced by isolated worker import paths and optional per-plugin
  dependency dirs.

## References

- [ADR 0004](0004-bmt-plugin-sdk-architecture.md)
- [ADR 0006](0006-plugin-abi-stability-contract.md)
- [ADR 0007](0007-plugin-packaging-discovery-layout.md)
- [ADR 0008](0008-plugin-capability-security-model.md)
