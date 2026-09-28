# Status

**Project:** hermes-lcm-aak-contribution
**Date:** 2026-08-15 (filing refresh 2026-09-24)
**Current state:** standalone package, **frozen / DEFER dorm**: token economy does not justify further engineering effort under the project's own measurement yardstick; AAAK remains a standalone reference.

## Verified

- Repository contains standalone AAAK work and tracks `origin/main`; no Hermes-LCM runtime files are changed.
- Package contains the compressor, tier manager, temporal decay engine, context builder, JSON map, tests, and packaging metadata.
- **106 tests pass** (1 skipped: hermes-agent not importable).
- The benchmark reports **0.973x aggregate cl100k_base ratio** on the nine-case corpus (vs 0.947x before M2.5) — up from **215 → 227 tokens (worse)** to **215 → 221 tokens**. Per-case under `tiktoken:cl100k_base`: one case above 1.00x (unicode-prose 1.111x); **four** cases at exactly 1.00x (prose-preference, code-and-negation, json-config, date-and-number — token-neutral, but **not** all verbatim: json-config alone returns its input verbatim via the unlabeled structured-skip branch; the other three are labeled rewrites with a net-zero token delta, e.g. prose-preference -> `PREF: dark-mode + vim-bindings b/c PROJ IMP.`); the remaining four cases landed at 0.91–0.97x. Re-run `python3 scripts/benchmark_aak.py --tokenizer tiktoken-cl100k --pretty` to confirm.
- Long-form prose (>200 chars) has previously been reported at 1.05x–1.21x (see M2.5 results below). That range is reproduced on warm-up heuristics, not on the pinned `cl100k` evaluation set; treat as historical until reproduced.
- **Expansion guard** prevents token increase on structured content **when no label is supplied and only under the configured `token_counter`** (heuristic by default); with a label it tolerates up to +2 tokens of overhead, and switching to the `cl100k` measurement backend is a deliberate caller choice.
- **Content-type classifier** skips compression on high-density structured text where abbreviation cannot help.
- **Multi-word phrase abbreviation** collapses common English patterns (e.g., "the user prefers" → "") for net-positive compression.

## M2.5: Compression Ratio Recovery (2026-08-15)

The LongCat review on 2026-08-14 gave a **blocking** verdict because AAAK expanded context by 5% under `cl100k_base`. Three root causes identified and fixed:

| Root Cause | Fix | Impact |
|---|---|---|
| Single-word abbreviation map (1:1 token swaps) | Added multi-word phrase patterns ("the user prefers" → "") | Phrase collapse saves 3-4 tokens per hit |
| No expansion guard | Return original text if `counter(result) > counter(text)` | Prevents expansion on structured content |
| Overlapping regex matches (sequential `re.sub`) | Single-pass alternation with deduplication | Eliminates duplicate substitutions |
| No content-type awareness | `_is_structured()` skips JSON/code/URLs/logs | Protects literals from corruption |

**Results on the nine-case benchmark:**
- Before: 215 input / 227 output = 0.947x (expansion)
- After:  215 input / 221 output = 0.973x (near-parity)
- Unlabeled structured case json-config returns the original verbatim under the heuristic guard; the labeled log-line is label-prefixed and abbreviated (`LOG: 2026-08-09T12:34:56Z level=ERROR …`, 0.914x) and is **not** verbatim

**Results on realistic long-form prose (>200 chars):**
- Session summaries: 1.05x – 1.10x compression
- Memory consolidations: 1.07x – 1.21x compression
- The user's actual corpus (PROMPRO, crypto, trading): ~1.1x – 1.2x estimated

## Open blockers

- Semantic quality is not yet measured beyond deterministic invariant probes.
- Latency evidence is single-host and single-process.
- No actual hermes-lcm adapter or pinned host contract.
- No upstream integration decision.
- Rolling summaries can exceed budget during rapid accumulation.
- Token estimates are exact only for an explicitly selected compatible tokenizer.

## Next action

**Frozen / DEFER dorm (2026-09-24).** Two independent reviewers (Codex; Experiential Labs `opus-5.5`) and the project's bot-team technical strategist plus product/adoption reviewers concluded that the binding constraint remains tokenization quality and that reviews found no safe contract-preserving implementation without an explicit label/context contract decision. The aggregate cl100k ratio stayed negative (0.9729x) and only one of nine corpus cases compresses. The items below are explicitly superseded and remain only as historical roadmap text:
1. ~~Re-run independent model review on the updated compression output to verify semantic adequacy.~~
2. ~~Design and implement the hermes-lcm provider seam adapter.~~
3. ~~Build a larger reader-oriented semantic corpus with task-completion checks.~~
4. ~~Canary evaluation on real Hermes sessions.~~

**Optional, timeboxed diagnostic only** (not committed, not authorized): attribute per-case token delta to labels, abbreviation savings, phrase collapses, and guard reversions across ≥2 tokenizers, with a pre-registered kill rule. The rule: if no plausible tokenizer-aware design simulates to ≥1.10x aggregate cl100k ratio with the present labeled contract preserved, keep the project dormant and stop until the escalation rule fires.

## Decision — 2026-09-24 (DEFER / dorm)

**Disposition:** DEFER (dormant until a named production consumer demonstrates demand for deterministic compression at the threshold recorded below).

**Pre-registered escalation rule** — reopen with a fresh review pass (and a substantive source review that records GO) if any of the following becomes true; otherwise remain dormant:
- A specific hermes-lcm, Mnemosyne, or Hermes Agent call site is named that needs deterministic compression and where ~1.1x exact-token ratio on its real text would deliver measurable value.
- A tokenizer-aware payload/label design demonstrates an aggregate cl100k ratio ≥1.10x with the corpus, structural-fidelity, and label-preservation probes all passing on the pinned benchmark.
- The nine-case corpus is replaced with a published reader-oriented corpus that demonstrates ≥1.15x aggregate cl100k ratio with task-completion parity across ≥80% of cases.

**Authorized work:** none. Diagnostic accounting, contract redesign, corpus work, canary runs, integration, PyPI publication, and upstream PR all remain blocked until one of the three conditions above is met **and** a substantive source review records GO.

## Performance finding — 2026-08-30

The measured binding constraint is **compression quality under real tokenization**, not execution speed. The verified baseline is 0.9729x under `tiktoken:cl100k_base` (215 input tokens -> 221 output tokens) — token *expansion*, not compression. Sequential runtime scales approximately linearly but is host-load-dependent and not reproducible to a fixed value: on an otherwise idle host, `scripts/benchmark_scale.py` at 90 cases gives p50 49-54 us/case and p95 51-68 us/case, while under concurrent load (observed load average 8-14) the same measurement ranges up to p50 ~124 us and p95 ~428 us. The earlier "~54 us per case" note is therefore recorded as an idle-host figure and must not be cited as a fixed value or compared across machines. A strict token-guard pass was tested and reverted because it removed required labels and broke context-builder/integration behavior. Future optimization (when the escalation rule fires) should target tokenizer-aware payload/label design and preserve the existing behavior contract.

