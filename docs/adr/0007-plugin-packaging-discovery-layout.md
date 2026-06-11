# ADR 0007: Plugin packaging, discovery, and naming (V2)

## Status

**Accepted** (2026-05-18)

## Context

Current plugin loading is convention-based on `projects/<project>/plugin.py`.
V2 requires explicit, versioned discovery and project-local extensibility for
complex plugin logic.

## Decision

1. Use project-local plugin package roots:
   - ``projects/<slug>/plugins/<plugin_slug>/`
2. Each plugin package includes:
   - `plugin.toml` (metadata),
   - `src/...` (implementation),
   - optional project-specific support modules.
3. Canonical plugin id format:
   - `<project>.<plugin_slug>` (example: `sk.keyword`).
4. Project registry file:
   - ``projects/<slug>/plugins/registry.yaml`.
5. Stage materialization emits per-project index:
   - `stage_root/projects/<project>/plugin-index.json`.
6. Preserve stage contract root:
   - `stage_root/projects/<project>/...` remains unchanged.

## Consequences

- Discovery becomes explicit and testable.
- Plugin naming becomes stable across manifests, logs, and reporting.
- Materialization and scaffold tooling must be updated.

## References

- [ADR 0005](0005-plugin-platform-v2-worker-runtime.md)
- [cloud-ci-handoff/docs/adding-a-project.md](../adding-a-project.md)
