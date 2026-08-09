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
