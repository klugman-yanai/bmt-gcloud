# Plugin Conformance Checklist

Use this checklist before enabling a new project in the cloud BMT pipeline.

Target plugin architecture: [`docs/plugins.md`](../../docs/plugins.md) and [ADR 0010](adr/0010-plugin-protocol-factory-api.md).

This document lives in **cloud-ci-handoff** because framework contracts, orchestration behavior, and CI gating are owned here.

---

## 1) Required Project Artifacts

- `projects/<slug>/project.bmt.json` with at least one entry under `bmts`
- Plugin implementation: ``projects/<slug>/plugin.py` — one `plugin()` factory
- Project-specific contract metadata belongs inside `project.bmt.json`.

## 2) Runner Execution Contract

- Runner invocation method documented (CLI args/env, optional batch mode).
- Per-case output artifact contract documented:
  - per-case metrics JSON path (for example `<output>.bmt.json`)
  - required fields (`status`, metric field(s), optional `exit_code`, optional `error`)
- If batch mode exists, batch schema documented and stable.

## 3) Scoring Contract (project-owned)

- Metric name(s) and direction are explicit (`higher_better` / `lower_better`).
- Aggregation rule is explicit (mean/median/pass-rate/etc.).
- Failure semantics are explicit:
  - case-level failure handling
  - all-cases-failed handling
  - baseline-absent behavior
- Reason codes are stable and readable in CI summaries.

## 4) Dataset Contract (project-owned)

- Input dataset location/prefix pattern defined (`inputs_prefix` on each BMT entry, or derived from the standard path).
- WAV files uploaded under that GCS prefix (runtime discovers `*.wav`, excludes `_prepared/`).
- Optional `dataset_manifest.json` for CI inventory only (not author-maintained).
- Channel/sample-rate assumptions declared in `plugin.py` audio prep.
- Required preconditions documented (for example refs optional/required).

## 5) Framework Integration Rules

- Primary scoring path uses structured JSON, not stdout regex parsing.
- Runner plugins declare their wake word as `keyword`; custom plugins can choose their own typed score fields in code.
- Execution policy uses the runtime default unless an advanced BMT entry explicitly overrides it.
- Plugin tuning/config does not require framework code edits for normal project work.

## 6) Required Tests Before Enablement

- Unit tests for plugin scoring/evaluation logic.
- Unit tests for metrics JSON parsing (valid, malformed, missing key).
- Execution tests for runner invocation adapter (success/failure/timeout).
- Dataset preflight tests (missing files/channel mismatch behavior).
- Batch parser tests (if batch mode enabled).
- One targeted integration test simulating a full leg result end-to-end.

## 7) CI Gate for Onboarding

- New project remains disabled by default until tests are green.
- Enablement change includes:
  - manifests + plugin + scoring + docs
  - test evidence (commands and pass output)
  - rollback plan (how to disable quickly)
- Required status context remains stable (`BMT Gate` unless explicitly changed).

## 8) Documentation Minimum

- Add project to `docs/adding-a-project.md` and docs index where relevant.
- Add project runtime notes (runner quirks, metrics schema, dataset assumptions).
- Include local run commands.
- Include known failure modes and where diagnostics are written.

## 9) Go / No-Go Definition

Project is **Go** only when all are true:

- Structured metrics contract is implemented and tested.
- Plugin scoring is deterministic and documented.
- Dataset contract validation passes.
- Targeted tests pass in CI.
- One cloud handoff run confirms expected `results/` and status reporting.
