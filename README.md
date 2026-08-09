# AAAK Compression Provider for hermes-lcm

> **Project status (2026-08-09):** standalone and not integrated into the active
> hermes-lcm runtime. See [`PRAXIS.md`](PRAXIS.md), [`ROADMAP.md`](ROADMAP.md),
> [`DECISIONS.md`](DECISIONS.md), and [`STATUS.md`](STATUS.md) for the governed
> integration path and current evidence.

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
pip install aaak-provider
```

```python
from aaak_provider import AAkCompressor, TierManager, ContextBuilder
from aaak_provider.compression import CompressionContext
from aaak_provider.tier_manager import TieredMemory, Tier

# Create compressor
compressor = AAkCompressor()

# Compress text
compressed = compressor.compress(
    "The user prefers dark mode and vim keybindings for coding",
    label="PREF"
)
# Result: "PREF: USR prefers dark-mode + vim-bindings for coding"

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
| Token reduction | Benchmark required | ~2-4x | ~5-10x |
| AI-readable | ✅ Native | ❌ Needs decoder | ✅ Native |
| Dependencies | stdlib only | Rust + PyO3 | LLM API/local |

## Integration with hermes-lcm

This package is designed as a candidate provider, but it is not currently integrated into the active hermes-lcm runtime. `ContextBuilder` is a package-local result type; an adapter and contract test are required before compatibility can be claimed.

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

56 tests currently cover compression, configuration validation, benchmark reporting, structural literal preservation, deterministic invariant probes, optional latency measurement, tier management, temporal decay, context building, and full pipeline integration. `SEMANTIC_EVALUATION.md` records a separate bounded adequacy review; it is not independent human or model-reader evidence. Sequential scale evidence is available through `scripts/benchmark_scale.py` and is explicitly host-local.

## License

Apache-2.0 — same as Lumina source.