# ADR 0004: BMT plugin SDK — single spec, honest loader, typed reporting

## Status

**Accepted** (2026-05-18), **superseded in architecture direction** by
[ADR 0005](0005-plugin-platform-v2-worker-runtime.md) on worker-isolated execution.
This ADR remains the historical baseline for the v1 direct-loader model.

## Context

Cloud BMT plugins load from `projects/<project>/plugin.py` and implement
`bmt_sdk.plugin.BmtPlugin`. Cloud Bench projects extend `RunnerPlugin`.
Historically, **two** configuration styles existed: a `Cloud BenchProjectPlugin` descriptor
(copied onto class attributes via `__init_subclass__`) **and** parallel
`ClassVar` fields on subclasses. That duplication made `plugin.py` harder to
read and could desynchronise `plugin_name` vs descriptor `name`.

The loader previously accepted `plugin_ref` and `allow_workspace` parameters
that were **ignored**, which confused contributors.

Reporting already depends on stable `ScoreResult.extra` keys (see
[ADR 0003](0003-score-extra-reporting-contract.md)), but the shapes are largely
`dict`-driven at authoring time, so drift between plugins and presentation is
possible.

## Decision

1. **Single static settings root** — `Cloud BenchProjectSettings` (`StrictPluginModel`)
   holds `ProjectIdentity`, `LegAudioPrep`, `RunnerExecutionConfig`. **Scoring**
   is a separate `scoring_policy: ClassVar[ScoringPolicyProtocol]` (see
   [plugin-config-model.md](../plugin-config-model.md)).

2. **Honest loader API** — `load_plugin(stage_root: Path, project: str)` only.
   Do **not** accept ignored parameters for backward compatibility. Historical
   manifest fields may remain in JSON; the loader does not branch on them
   unless a future ADR restores real behavior.

3. **Typed scoring policy snapshots** — Introduce SDK types (e.g. Pydantic
   `ScoringPolicyRecord`) for `extra["scoring_policy"]`, produced by scoring
   policies and consumed when building `ScoreResult`. Presentation stays
   generic per ADR 0003.

4. **Stable lifecycle** — Keep `prepare` → `execute` → `score` → `evaluate` on
   `BmtPlugin`. Keep the runner JSON contract in `cloud_bench_runner_contract`
   stable relative to core-main.

## Consequences

- **Breaking change** for plugin authors who use the legacy `ClassVar` pattern
  or call `load_plugin` with old signatures. All in-repo projects
  (`projects/sk`, `projects/skyworth`, `examples`) move in lockstep.
- **Documentation** — `sdk/README.md`, `plugin-config-model.md`, `adding-a-project.md`,
  and the template project follow the settings + scoring layout.
- **External consumers** of a published `bmt_sdk` package require a **major**
  version bump and a short migration note (settings model + loader).

## References

- [`plugin-config-model.md`](../plugin-config-model.md) — configuration deep dive
- [`plugin-sdk-architecture.md`](../plugin-sdk-architecture.md) — pipeline / loader architecture
- [ADR 0003](0003-score-extra-reporting-contract.md) — `ScorePayload.extra` contract
- [`runtime/plugin_loader.py`](../../runtime/plugin_loader.py) — loader implementation
- [`sdk/bmt_sdk/cloud_bench/`](../../sdk/bmt_sdk/cloud_bench/) — Cloud Bench runner SDK helpers
