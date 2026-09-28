# Decisions

## 2026-08-09 — Keep AAAK standalone until the adapter is proven

**Decision:** Do not integrate AAAK into active hermes-lcm yet.

**Reasoning:** hermes-lcm is a lossless SQLite/DAG context engine with source-aware recovery. AAAK is a lossy, deterministic text compressor with an independent in-memory tier model. The current package README's claim that `ContextBlock` is compatible is not evidence of an actual host contract. A narrow adapter and canary are safer than copying tiers/storage into hermes-lcm.

**Reversible:** Yes. The package remains independently installable and can be disabled without host changes.

## 2026-08-09 — Evidence before the 30x headline

**Decision:** Treat `~30x` as an unverified target until measured across a published corpus with a named tokenizer and distribution statistics.

**Reasoning:** Character heuristics are not tokenizer counts, and aggressive filler/abbreviation substitution can damage identifiers, literals, negation, dates, URLs, or code. Existing memory benchmark practice evaluates recall and temporal/multi-hop behavior, not only size reduction.

## 2026-08-09 — Preserve raw-source ownership in the host

**Decision:** AAAK may compress a provider-visible block, but it must not become the owner of hermes-lcm raw messages, source lineage, or durable recovery records.

**Reasoning:** Lumina's closets/drawers separation is useful prior art; hermes-lcm already has a stronger lossless store/DAG contract. Duplicating persistence would create divergent truth and migration risk.

## 2026-08-09 — Low-risk hardening accepted

**Decision:** Fix package importability under pytest, word-boundary corruption, ignored custom filler configuration, and invalid decay-rate handling.

**Reasoning:** These are local, backward-compatible correctness/testability fixes with direct regression tests. They do not change the host integration surface.

## 2026-08-30 — Prioritize tokenization quality over runtime optimization

**Finding:** AAAK's binding constraint is compression quality under real tokenization, not execution speed.

**Evidence:** The verified `tiktoken:cl100k_base` baseline is 215 input -> 221 output tokens (0.9729x), while sequential compression remains approximately linear and host-load-dependent: on an idle host `scripts/benchmark_scale.py` at 90 cases gives p50 49-54 us/case and p95 51-68 us/case, rising to roughly p50 ~124 us / p95 ~428 us under load average 8-14, so the earlier "~54 us per case" note is recorded as an idle-host figure rather than a fixed value. A strict no-expansion guard improved the isolated ratio probe but caused five existing behavior regressions, including lost labels and broken context-builder/integration expectations; the pass was reverted.

**Decision:** Do not pursue a runtime-speed optimization next. Prioritize a tokenizer-aware payload/label design, with regression coverage for labels, context assembly, structural fidelity, and exact-token behavior.

**Status:** Superseded by 2026-09-24 DEFER decision (next).

## 2026-09-24 — Freeze AAAK as a standalone reference (DEFER / dorm)

**Disposition:** DEFER until a named production consumer demonstrates demand for deterministic compression at the recorded threshold; meanwhile AAAK remains a standalone reference.

**Evidence:**
- Independent technical strategist reproduced `benchmark_aak.py --tokenizer tiktoken-cl100k`: aggregate ratio 0.9729x; per-case one case above 1.00x (unicode-prose 1.111x); the remaining cases land at or below 1.00x with several at pass-through or expansion despite the heuristic expansion guard.
- Independent product/adoption reviewer (also `glm-5.3-flash`) found no hermes-lcm, Mnemosyne, or Hermes Agent call site that needs ~1.1x deterministic compression, and the ~30x headline claim is contradicted by the same benchmark.
- Two model reviews (Codex, Experiential Labs `opus-5.5`) concluded **reviews found no safe contract-preserving tokenizer-aware implementation without an explicit label/context contract decision**.

**Decision rationale:** With the binding constraint classified, no production-bound change authorized, and the existing tests/harness/corpus already preserved as documentation, the cheapest terminal state is a documented dorm, not a long redesign that loses to free LLM summarization on value.

**Reversible:** Yes. The repository, tests, benchmark harness, status docs, and ability to file a new wiki checkpoint remain intact; the package is still installable and importable. Reopening is gated by the escalation rule and a substantive source review.

**Escalation rule:** reopen the project only if any of (a)–(c) fires **and** a substantive source review records GO:
- (a) a specific call site is named that needs deterministic compression at ~1.1x exact-token ratio on its real text,
- (b) a tokenizer-aware design demonstrates ≥1.10x aggregate cl100k ratio on the pinned corpus while preserving the label contract, or
- (c) a published reader-oriented corpus demonstrates ≥1.15x aggregate cl100k ratio with task-completion parity across ≥80% of cases.
