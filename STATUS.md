# Status

**Project:** hermes-lcm-aak-contribution
**Date:** 2026-08-09
**Current state:** standalone package; not integrated into hermes-lcm.

## Verified

- Repository contains uncommitted standalone AAAK work and tracks `origin/main`; no Hermes-LCM runtime files are changed.
- Package contains the compressor, tier manager, temporal decay engine, context builder, map, tests, and packaging metadata.
- Baseline test invocation from the checkout was not importable without path setup; `pyproject.toml` now declares the project root for pytest.
- After benchmark expansion, JSON structural-literal protection, configuration hardening, semantic-probe reporting, and optional latency measurement, the suite passes: **56 tests**.
- The nine-case benchmark reports **1.0568x aggregate heuristic ratio** using `max(1, len(text) // 4)`, median ratio `1.0`, corpus SHA-256 `94b267e9067b275abb77725b0cdd3c4f463c1babf4b64cfbae886685a9e2a7e3`, structural fidelity PASS, semantic probes PASS, and deterministic-output PASS.
- Optional `tiktoken:cl100k_base` measurement is executable in `.venv`: aggregate ratio **0.9471x**, median ratio **0.9524**, 215 input tokens versus 227 output tokens, structural fidelity PASS, semantic probes PASS, and deterministic-output PASS. This is tokenizer-accurate for `cl100k_base`, not a full semantic-quality result and not necessarily the target reader's tokenizer.
- With 20 timed samples per case and one warm-up, the `cl100k_base` run reports median case p50 **190.259 µs** and median case p95 **193.037 µs** using `time.perf_counter_ns`. These are local wall-clock observations, not a portable performance guarantee.
- Sequential scaling evidence is available via `scripts/benchmark_scale.py`: with 30 repeats, per-case p50 was **149.278 µs** for one case, **168.327 µs** for nine cases, and **168.251 µs** for 90 cases; total p50 was **149.278 µs**, **1514.943 µs**, and **15142.598 µs**, respectively. This indicates near-linear work at larger corpus sizes, but remains single-host and single-process evidence.
- `SEMANTIC_EVALUATION.md` records a fresh-context independent model review of all nine cases: six adequate, three borderline, and none inadequate. Cases 1, 2, and 8 need shorthand expansion or map documentation for standalone readers. This is not independent human or reader task-completion evidence.
- Wheel build and fresh-environment installation pass. Installed-artifact import/configuration smoke tests and the source-checkout benchmark CLI pass. Packaging metadata emits no deprecation warnings after switching to SPDX license metadata.

## Open blockers

- Semantic quality is not yet measured beyond deterministic invariant probes; no human or model-based adequacy evaluation exists.
- Latency evidence is single-host and single-process; no repeated-run distribution, concurrency, or scale study exists.
- No actual hermes-lcm adapter or pinned host contract.
- No upstream integration decision.
- Rolling summaries are append-only and can violate the stated budget.
- Token estimates are exact only for an explicitly selected compatible tokenizer.
- No CI workflow, changelog, or license file was tracked in the original project.

## Next action

Complete the bounded semantic-adequacy evaluation, then decide whether the
evidence justifies designing an adapter. Keep Hermes-LCM integration disabled.
