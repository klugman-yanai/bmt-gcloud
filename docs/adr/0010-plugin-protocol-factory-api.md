# ADR 0010: Plugin Protocol + function factory discovery

**Status:** Accepted  
**Date:** 2026-05-20  
**Supersedes:** ClassVar / subclass discovery guidance in ADR 0004 (authoring only; pipeline placement unchanged)

## Context

Plugin authors previously subclassed `RunnerPlugin`, assigned `ClassVar[Cloud BenchProjectSettings]`
and `ClassVar[ScoringPolicy]`, and relied on the runtime to scan `plugin.py` for exactly one
`BmtPlugin` subclass. That pattern was hard to read and easy to misconfigure.

## Decision

1. **`BmtPlugin` is a `@runtime_checkable` Protocol** — four hooks plus `plugin_name`, `api_version`,
   and `cloud_task: CloudTaskSpec`.

2. **Function factory discovery** — each `plugin.py` exports `plugin()` returning a `BmtPlugin`.
   Typical workload plugins return `cloud_bench_runner(project=..., audio=...)`; custom OEMs return
   `custom_plugin(...)` with hook callables.

3. **Factories** — `cloud_bench_runner(...)` and `custom_plugin(...)` build implementations directly.

4. **Loader** — `load_plugin_from_module()` in `bmt_sdk/discovery.py` calls `plugin()` and verifies
   that it returns `BmtPlugin`.

5. **SDK layout** — runner-specific helpers live under `bmt_sdk/cloud_bench/*` with internal
   `_RunnerPluginImpl`.

## Consequences

- **Breaking:** `RunnerPlugin`, `Cloud BenchProjectSettings`, subclass discovery, scattered module attrs,
  and `PLUGIN` export removed.
- **Worker scaffold** imports `plugin.py` and calls `load_plugin_from_module(module)`.
- **Plan-time cloud task** loads the plugin and reads `cloud_task.for_slug(bmt_slug)`.
- **Strong typing:** audio prep, runner config, scoring policy, and cloud task validated when
  `plugin()` constructs the plugin.

## References

- [`docs/plugins.md`](../../docs/plugins.md)
- [`sdk/bmt_sdk/discovery.py`](../../sdk/bmt_sdk/discovery.py)
- [`sdk/bmt_sdk/plugin.py`](../../sdk/bmt_sdk/plugin.py)
