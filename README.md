# AAAK Compression Provider for hermes-lcm

> **Project status (2026-08-09; updated 2026-09-24):** standalone, **frozen / DEFER dorm**, not integrated into the active
> hermes-lcm runtime. See [`PRAXIS.md`](PRAXIS.md), [`ROADMAP.md`](ROADMAP.md),
> [`DECISIONS.md`](DECISIONS.md), and [`STATUS.md`](STATUS.md) for the governed
> path and the 2026-09-24 dorm decision / escalation rule.

Deterministic, AI-readable compression without requiring a decoder. The historical
`~30x` reduction is an unverified target; run the benchmark and inspect its named
token-measurement method before making reduction claims. Adapted from Lumina MemPalace
(Bino5150/lumina).

## Overview

This provider implements an alternative compression strategy for hermes-lcm that:

- **Historical ~30x reduction target** — unverified; the current baseline benchmark reports its measurement method and result
- **Requires zero LLM calls** — deterministic, sub-millisecond
- **Is natively AI-readable** — no decoder needed, LLMs understand the shorthand directly
- **Uses explicit tier budgets** (L0-L3) matching Lumina's 4-layer architecture
- **Supports rolling summaries** (Lumina's "closet" pattern) to bound context growth
- **Includes temporal decay** for recency-weighted retrieval
- **Adds a "nightstand" tier** for auto-generated content with promotion gates

## Quick Start

```bash
# From this checkout (PyPI publication is not authorized under the 2026-09-24 dorm):
pip install -e .
```

```python
from aaak_provider import AAkCompressor, TierManager, ContextBuilder, CompressionContext
from aaak_provider.tier_manager import TieredMemory, Tier

# Create compressor
compressor = AAkCompressor()

# Compress text
compressed = compressor.compress(
    "The user prefers dark mode and vim keybindings for coding",
    label="PREF"
)
# Actual verified output: "PREF: dark-mode + vim-bindings for coding"
# (Verified 2026-09-28 by execution. The comment previously shown here —
#  "PREF: USR prefers dark-mode + vim-bindings for coding" — is stale: the
#  multi-word phrase abbreviations map "the user prefers" to "" and "dark mode"
#  to "dark-mode", so `USR` and `prefers` no longer appear in the output.)

# Build context with tier budgets
tier_manager = TierManager()
builder = ContextBuilder()

memories = [
    TieredMemory(content="User identity: Alice", tier=Tier.IDENTITY, label="IDENTITY", token_estimate=10, timestamp="..."),
    TieredMemory(content="Prefers dark mode", tier=Tier.CRITICAL, label="PREF", token_estimate=8, timestamp="..."),
]

context = CompressionContext(session_id="test", max_tokens=500)
block = builder.build_context_block(memories, context)
```

## Architecture

### 4-Layer Tier System (Lumina L0-L3)

| Tier | Tokens | Injection | Purpose |
|------|--------|-----------|---------|
| **identity** | 50 | Always | Agent/user identity, platform, stack |
| **critical** | 120 | Always | Preferences, active project, critical facts |
| **recent** | 300 | Session start | Recent sessions, decay-sorted |
| **nightstand** | 200 | Optional | Auto-sweeps, reviewable, promotion-gated |
| **deep** | ∞ | Never | Verbatim originals, on-demand search |

### Rolling Summary Pattern

Instead of creating new summary nodes per consolidation, AAAK updates a single rolling summary per topic (pipe-separated AAAK facts). This bounds DAG complexity and injection size.

### Temporal Decay

Exponential forgetting curve: `w(t) = e^(-λ × t)` with λ=0.05/day (~22% retention at 30 days).

## Comparison

| Dimension | AAAK | Caveman (rust_cave_001) | LLM Summarization |
|-----------|------|------------------------|-------------------|
| Deterministic | ✅ | ✅ | ❌ |
| LLM calls | 0 | 0 | 1+ per consolidation |
| Latency | <1ms | ~5-10ms | 500ms-5s |
| Token reduction | **Benchmark required — measured 0.9729x (expansion)** | "~2-4x" not measured in this project; carried over unverified | ~5-10x |
| AI-readable | ✅ Native | ❌ Needs decoder | ✅ Native |
| Dependencies | stdlib only | Rust + PyO3 | LLM API/local |

_Verification note (2026-09-28):_ the AAAK token-reduction cell is filled from this
project's own `cl100k_base` measurement. The Caveman `~2-4x` cell has **not**
been measured against a tokenizer here and is an unverified figure carried
over from the original comparison; a head-to-head exact-token comparison has
never been run. Treat the Caveman and LLM columns as unquantified.

## Integration with hermes-lcm (historical, subject to the 2026-09-24 dorm)

This package is designed as a candidate provider, but it is not currently integrated into the active hermes-lcm runtime. `ContextBuilder` is a package-local result type; an adapter and contract test are required before compatibility can be claimed. Per the 2026-09-24 dorm decision (`STATUS.md`, `DECISIONS.md`), the integration proposals below are retained as historical context only.

### Proposed Integration Points

1. **Provider registration** — Add `aaak` as a compression provider option
2. **Config schema** — Extend hermes-lcm config with `aaak:` section for tier budgets, abbreviation map path, decay rate
3. **Context assembly** — `ContextBuilder.build_context_block()` replaces/supplements existing tier logic
4. **Rolling summaries** — Store in hermes-lcm externalized payloads or new summary node type

## Compressor configuration contract

`AAkConfig` validates abbreviation maps, filler words, and `min_line_length`
before compression starts. Abbreviation-map keys and values must be non-empty,
single-line strings; keys must be unique case-insensitively; and an empty map is
rejected. `min_line_length` must be a non-negative integer. `create_compressor()`
rejects unknown configuration keys and malformed values. Custom filler words
provided through the factory extend the default filler set; an explicit
`AAkConfig(filler_words=...)` supplies the exact filler set. JSON abbreviation
maps replace the current map only after successful validation.

## Source Attribution

All core algorithms adapted from **Lumina (Bino5150/lumina)**:
- `tools/palace.py` — AAAK engine, palace CRUD, tier logic
- `core/dreaming.py` — Idle sweep, nightstand, human profile curation
- `tools/temporal_decay.py` — Exponential decay weighting

Licensed Apache-2.0.

## Testing

The deterministic baseline benchmark is:

```bash
python3 scripts/benchmark_aak.py --pretty
```

It uses a named heuristic by default. For an optional `cl100k_base` tokenizer
measurement, install the benchmark extra and run:

```bash
uv pip install -e '.[benchmark]'
python3 scripts/benchmark_aak.py --tokenizer tiktoken-cl100k --pretty
```

The tokenizer is never loaded implicitly, and `cl100k_base` is a measurement
backend rather than a claim that it matches every target reader model.

```bash
./scripts/verify.sh
```

**Historical (2026-08-15)** 56 tests previously covered compression, configuration validation, benchmark reporting, structural literal preservation, deterministic invariant probes, optional latency measurement, tier management, temporal decay, context building, and full pipeline integration. **Current (2026-09-24)** 106 tests pass and 1 is skipped (the hermes-agent import is unavailable); see `scripts/verify.sh` output. `SEMANTIC_EVALUATION.md` records a separate bounded adequacy review; it is not independent human or model-reader evidence. Sequential scale evidence is available through `scripts/benchmark_scale.py` and is explicitly host-local.

> **2026-09-24 update:** The verdict-driving target on the roadmap is now superseded by the dorm decision recorded in `STATUS.md` and `DECISIONS.md`. The package is retained in this repository as a standalone reference of a deterministic, stdlib-only compressor that measured a 0.9729x aggregate `cl100k` ratio on the nine-case benchmark; the 1.05x–1.21x long-form figure is **historical** (heuristic warm-up measurements, never reproduced on the pinned `cl100k` set — see ROADMAP Milestone 1.5). Further tokenizer-aware engineering is gated on the named-demand escalation rule.

## License

Apache-2.0 — same as Lumina source.