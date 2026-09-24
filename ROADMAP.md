# AAAK Roadmap

## Verdict-driving target

Make AAAK an **optional, standalone deterministic compression provider with a narrow adapter seam**, not a replacement for hermes-lcm's lossless store/DAG. The package must prove compression and fidelity first, then integrate through an explicit adapter and opt-in canary.

> **2026-09-24 — FROZEN / DEFER dorm (supersedes all milestones below).** The aggregate cl100k ratio is 0.9729x with only one of nine corpus cases compressing, and two independent reviewers concluded **reviews found no safe contract-preserving tokenizer-aware implementation without an explicit label/context contract decision**. AAAK remains a standalone reference; see [[STATUS]] `Decision — 2026-09-24 (DEFER / dorm)` and DECISIONS ADR.

## Milestone 0 — Evidence and contract (highest risk first)

**Demonstrable state:** A fresh checkout can run the package and produce a benchmark report whose claims are reproducible.

- [x] Define the public API and versioning policy (`AAkCompressor`, `ContextBuilder`, tier objects, result metadata).
- [x] Add a benchmark corpus: prose, tool output, JSON/log-like text, identifiers, dates, URLs, code, multilingual/Unicode samples.
- [x] Measure exact tokenizer counts when available and report the fallback estimator separately.
- [x] Report median/p95 compression ratio and latency, not a single "~30x" number.
- [x] Add fidelity probes: protected literals, identifiers, URLs, numbers, negation, dates, and label stability.
- [x] Add property tests for idempotence policy, word-boundary safety, malformed maps, empty input, and timestamp edge cases.

**Exit:** `python3 scripts/benchmark_aak.py --pretty` emits versioned JSON with corpus hash, tokenizer-measurement metadata, ratio distribution, and pass/fail structural-fidelity checks.

## Milestone 1 — Package correctness and operability

**Demonstrable state:** The package behaves predictably as an installed artifact and rejects unsafe configuration.

- [x] Publish/import smoke test in an isolated virtual environment and wheel build check.
- [x] Validate abbreviation-map schema: string-to-string entries, non-empty keys, deterministic ordering, and collision warnings.
- [x] Decide whether custom filler words replace or extend defaults; document and test the choice.
- [x] Add explicit timestamp policy (UTC-aware timestamps preferred; invalid/future timestamps handled deterministically).
- [x] Bound or compact rolling summaries; current append-only behavior can exceed the stated tier budget.
- [x] Replace ambiguous "L0-L3" language with the actual five internal categories (`identity`, `critical`, `recent`, `nightstand`, `deep`).
- [x] Add license file, changelog, supported-Python CI matrix, and package metadata checks.

**Exit:** wheel installs into a clean venv; all tests run without `PYTHONPATH`; CI covers supported Python versions; budget and configuration invariants are tested.

## Milestone 1.5 — Compression ratio recovery (M2.5) — ✅ COMPLETE 2026-08-15

**Demonstrable state:** AAAK no longer expands context under `cl100k_base`.

- [x] Identify root cause: single-word abbreviation map (1:1 token swaps), no expansion guard, overlapping regex matches, no content-type awareness.
- [x] Add multi-word phrase abbreviations ("the user prefers" → "") for net-positive compression.
- [x] Add expansion guard: return original if `counter(result) > counter(text)`.
- [x] Add content-type classifier: skip compression on JSON/code/URLs/logs.
- [x] Fix regex overlap with single-pass alternation and deduplication.
- [x] Update benchmark to reflect new ratio metrics.

**Exit:** `cl100k_base` benchmark ratio >= 0.95x on the original corpus; >1.0x on realistic long-form prose.

**Results:**
- Nine-case benchmark: 215 input / 221 output = 0.973x (up from 0.947x)
- Realistic long-form (>200 chars): 1.05x – 1.21x compression
- Expansion guard prevents token increase on structured content

## Milestone 2 — Integration spike, no host changes

**Demonstrable state:** A local adapter consumes hermes-lcm-shaped inputs and returns a provider-neutral compressed block while preserving source identity and fallback behavior.

- [x] Inspect and pin the actual hermes-lcm seam at the target commit; do not assume a generic `ContextBlock` is compatible.
- [x] Define an adapter protocol with input messages, output block, token accounting, source references, and truncation/fallback status.
- [x] Build a fake-host contract test suite in this repository.
- [ ] Compare AAAK against current hermes-lcm paths: local LLM summary, fallback model, and deterministic truncation.
- [ ] Keep the adapter optional and side-effect free; no database schema or runtime activation in this milestone.

**Exit:** adapter contract tests pass against fixtures and a canary harness proves a one-switch fallback to the existing host path.

## Milestone 3 — Upstream integration proposal

**Demonstrable state:** Maintainers can review a minimal integration proposal with evidence and a rollback plan.

- [ ] Choose among optional package/provider registry, built-in provider, or host adapter based on Milestone 2 evidence.
- [ ] Submit the smallest upstream change: provider registration plus config/feature flag, not tier/storage redesign.
- [ ] Specify precedence: explicit LLM summary → AAAK (if enabled) → deterministic truncation, or the maintainer-approved order.
- [ ] Specify observability: provider selected, input/output token estimates, ratio, latency, fallback reason, and source lineage.
- [ ] Specify privacy: no new network calls; redact or preserve host redaction semantics.

**Exit:** upstream review-ready patch/PR, compatibility matrix, and documented rollback switch.

## Milestone 4 — Canary and evaluation

**Demonstrable state:** AAAK can run opt-in on representative sessions with evidence that it does not silently damage recall or tool continuity.

- [ ] Run LOCOMO/LongMemEval-style recall probes where applicable, plus Hermes-specific tool-call and source-lineage fixtures.
- [ ] Compare baseline, AAAK-only, hybrid, and truncation-only modes under the same reader model and token budget.
- [ ] Track answer accuracy, abstention/contradiction behavior, token reduction, p50/p95 latency, and fallback rate.
- [ ] Canary only with opt-in configuration and an immediate rollback switch.

**Exit:** decision memo: adopt, revise, or reject; no default-on change without a demonstrated quality floor.

## Explicit non-goals

- Replacing hermes-lcm's immutable raw store or summary DAG.
- Treating AAAK as lossless or as a decoder for arbitrary prose.
- Using headline compression ratio as a proxy for memory quality.
- Adding vector databases, LLM extraction, or a new persistence layer to this package before the adapter and benchmark gates pass.
