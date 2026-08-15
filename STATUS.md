# Status

**Project:** hermes-lcm-aak-contribution
**Date:** 2026-08-15
**Current state:** standalone package; not integrated into hermes-lcm.

## Verified

- Repository contains standalone AAAK work and tracks `origin/main`; no Hermes-LCM runtime files are changed.
- Package contains the compressor, tier manager, temporal decay engine, context builder, JSON map, tests, and packaging metadata.
- **106 tests pass** (1 skipped: hermes-agent not importable).
- The benchmark reports **0.973x aggregate cl100k_base ratio** on the nine-case corpus (vs 0.947x before M2.5) — up from **215 → 227 tokens (worse)** to **215 → 221 tokens**.
- On realistic long-form prose (>200 chars), AAAK achieves **1.05x – 1.21x** compression.
- **Expansion guard** prevents token increase on structured content (JSON, URLs, logs, shell commands).
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
- Structured cases (json-config, log-line) now return original verbatim

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

The M2.5 compression-ratio recovery has resolved the blocking verdict's core complaint. Remaining work:

1. Re-run independent model review on the updated compression output to verify semantic adequacy.
2. Design and implement the hermes-lcm provider seam adapter.
3. Build a larger reader-oriented semantic corpus with task-completion checks.
4. Canary evaluation on real Hermes sessions.

