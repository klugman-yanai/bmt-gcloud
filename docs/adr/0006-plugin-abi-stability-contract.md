# ADR 0006: Plugin ABI stability contract (V2 worker)

## Status

**Accepted** (2026-05-18)

## Context

V2 introduces a worker boundary. Without a strict ABI contract, runtime and
plugin package upgrades can drift and fail late in cloud runs.

## Decision

1. Define an explicit plugin ABI with version negotiation:
   - `plugin_api_version` uses semantic major/minor.
   - Runtime accepts only compatible major versions.
2. Treat these as **stable ABI**:
   - Hook RPC method names: `prepare`, `execute`, `score`, `evaluate`.
   - Request/response envelope schemas.
   - `ExecutionResult`, `ScoreResult`, `VerdictResult` wire-compatible fields.
3. Treat these as **evolving contract**:
   - Optional capability descriptors and telemetry extensions.
   - Optional helper endpoints (for diagnostics) behind feature flags.
4. Fail fast on incompatibility at plan/task handoff:
   - No partial run should begin when ABI compatibility is unknown.

## Consequences

- Platform gets deterministic compatibility behavior.
- SDK and runtime can evolve independently within the same major ABI.
- Plugin authors receive clearer migration boundaries.

## References

- [ADR 0005](0005-plugin-platform-v2-worker-runtime.md)
- [ADR 0003](0003-score-extra-reporting-contract.md)
