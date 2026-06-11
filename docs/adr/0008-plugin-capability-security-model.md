# ADR 0008: Plugin capability and security model (V2)

## Status

**Accepted** (2026-05-18)

## Context

Advanced plugins need network access, secrets, and external services. Today,
those concerns are ad hoc in plugin code and not represented as runtime policy.

## Decision

1. Introduce capability-scoped plugin execution:
   - network profile,
   - secrets scope,
   - storage scope,
   - timeout/retry budget.
2. Runtime provides a capability broker to workers; raw ambient runtime context
   is not exposed by default.
3. Plugin metadata declares required capabilities in `plugin.toml`.
4. Runtime enforces capability policy before hook execution.
5. Standard telemetry emitted per hook:
   - plugin id, phase, duration, retry count, failure class.

## Consequences

- Security posture improves through explicit least-privilege controls.
- Runtime gains consistent observability for plugin operations.
- Plugin authors must declare capabilities up front and handle policy errors.

## References

- [ADR 0005](0005-plugin-platform-v2-worker-runtime.md)
- [ADR 0006](0006-plugin-abi-stability-contract.md)
