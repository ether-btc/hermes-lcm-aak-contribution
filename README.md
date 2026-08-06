# AAAK Compression Provider for hermes-lcm

Deterministic, AI-readable compression achieving ~30x token reduction without requiring a decoder. Adapted from Lumina MemPalace (Bino5150/lumina).

## Overview

This provider implements an alternative compression strategy for hermes-lcm that:

- **Achieves ~30x token reduction** on verbose prose
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
| Token reduction | ~30x (prose) | ~2-4x | ~5-10x |
| AI-readable | ✅ Native | ❌ Needs decoder | ✅ Native |
| Dependencies | stdlib only | Rust + PyO3 | LLM API/local |

## Integration with hermes-lcm

This provider is designed to plug into hermes-lcm's compression interface. The `ContextBuilder` produces `ContextBlock` objects compatible with hermes-lcm's context assembly pipeline.

### Proposed Integration Points

1. **Provider registration** — Add `aaak` as a compression provider option
2. **Config schema** — Extend hermes-lcm config with `aaak:` section for tier budgets, abbreviation map path, decay rate
3. **Context assembly** — `ContextBuilder.build_context_block()` replaces/supplements existing tier logic
4. **Rolling summaries** — Store in hermes-lcm externalized payloads or new summary node type

## Source Attribution

All core algorithms adapted from **Lumina (Bino5150/lumina)**:
- `tools/palace.py` — AAAK engine, palace CRUD, tier logic
- `core/dreaming.py` — Idle sweep, nightstand, human profile curation
- `tools/temporal_decay.py` — Exponential decay weighting

Licensed Apache-2.0.

## Testing

```bash
pytest tests/ -v
```

26 tests covering compression, tier management, temporal decay, context building, and full pipeline integration.

## License

Apache-2.0 — same as Lumina source.