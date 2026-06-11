# ADR 0009: Direct plugin execution (default)

## Status

**Accepted** (2026-05-20). Partially supersedes worker-only wording in [ADR 0005](0005-plugin-platform-v2-worker-runtime.md).

## Context

Per-project `plugins/default/.../worker.py` packages duplicated the same delegation logic and forced authors to understand registry, plugin-index, and worker ABI even when `plugin.py` already defined the full plugin.

## Decision

1. **Default runtime:** Cloud Run executes `projects/<slug>/plugin.py` in-process via `runtime/plugin_host/direct_client.py` and `load_plugin_direct`.
2. **Single runtime entrypoint:** Cloud Run always loads `projects/<slug>/plugin.py` as the plugin entrypoint.
3. **Project-owned module layout:** projects may import local submodules from `plugin.py` and declare third-party dependencies in standard Python project files (`pyproject.toml` or `requirements.txt`).
4. **Materialize:** plugin package metadata/index files may still be staged for tooling, but they do not change runtime entrypoint resolution.

## Consequences

- New Cloud Bench projects commit `plugin.py` + leg JSON only; no worker tree in git.
- `add-plugin-package` remains available for packaging/tooling workflows, but runtime execution still starts at `plugin.py`.
- Leg JSON omits platform fields (`plugin_id`, `plugin_version`); scaffold does not emit them.

## References

- [ADR 0004](0004-bmt-plugin-sdk-architecture.md)
- [ADR 0005](0005-plugin-platform-v2-worker-runtime.md)
- [docs/plugins.md](../../docs/plugins.md)
