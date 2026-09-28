# Contribution Proposal: AAAK Compression Provider for hermes-lcm

> **Status: frozen / DEFER dorm (2026-09-24). Not an open proposal.**
> This document is preserved as the original 2026-08-06 pitch. Its headline
> performance claim is **disproved by measurement** and every *historical
> performance* statement below is superseded by these figures. AAAK is currently measured at
> **0.9729x aggregate exact-token compression** (215 input → 221 output
> tokens under `tiktoken:cl100k_base`) — that is token *expansion*, not
> compression. No integration, PyPI publication, or upstream PR is
> authorized. See `DECISIONS.md` ADR 2026-09-24 for the dorm decision and
> the pre-registered escalation rule that would reopen this work.
> Current verification: `./scripts/verify.sh` → **106 passed, 1 skipped**.

## Summary

This proposal introduces **AAAK (AI-readable Algorithmic Abbreviation & Keyword) compression** as a new deterministic compression provider for hermes-lcm. Adapted from Lumina MemPalace (Bino5150/lumina, Apache-2.0), AAAK offers deterministic compression without any LLM calls, with output formatted for machine readability. ~~AAAK achieves ~30x token reduction on verbose prose~~ — **this claim was measured and rejected; see the status banner above.**

## Motivation

Current hermes-lcm compression options:
- **LLM summarization** — High quality but requires LLM calls (latency, cost, availability)
- **Caveman (rust_cave_001)** — Deterministic, output needs a decoder; its "~2-4x" figure has **not** been measured against a tokenizer in this project and is carried over unverified

_Original 2026-08-06 claim, now withdrawn: AAAK fills a gap of
deterministic + high compression + AI-native readability. Only the
determinism holds up under measurement; the compression does not. A
head-to-head exact-token comparison against Caveman remains unperformed
and would be required before any gap claim could be re-asserted._

## What This Provides

### 1. AAAK Compression Engine (`aaak_provider/compression.py`)
- Deterministic abbreviation map (longest-match-first)
- Filler word stripping
- Label-prefixed output (PREF:, PROJ:, SESS:, etc.)
- ~~~30x reduction on prose~~ — **disproved by measurement** (0.9729x aggregate exact-token). Sub-millisecond latency is real but host-load-dependent and not exactly reproducible (`scripts/benchmark_scale.py`, 90 cases: p50 49–54 µs/case, p95 51–68 µs/case across runs) — it has no value without actual savings
- Extensible abbreviation map (JSON file or runtime API)

### 2. 4-Layer Tier Manager (`aaak_provider/tier_manager.py`)
- Explicit token budgets per tier (identity:50, critical:120, recent:300, nightstand:200, deep:∞)
- Rolling summary pattern (Lumina "closet" — pipe-separated AAAK facts per topic)
- Budget enforcement with temporal decay sorting
- Nightstand tier for auto-generated content (budget-enforced; "promotion gates" are design intent — `promotion-gated` appears only in `tier_manager.py:18,64` and `host_adapter.py:421` docstrings, with no implementation and no test in `aaak_provider/`)

### 3. Temporal Decay Engine (`aaak_provider/temporal_decay.py`)
- Exponential forgetting: `w(t) = e^(-λ × t)` with configurable λ (default 0.05/day)
- Sort-by-recency for recent/nightstand tiers
- Weight filtering

### 4. Context Builder (`aaak_provider/context_builder.py`)
- Builds injection-ready `ContextBlock` compatible with hermes-lcm context assembly
- Respects tier order, budgets, focus topics, overrides
- Returns truncated indicator for downstream handling

### 5. Comprehensive Test Suite (106 tests passing, 1 skipped as of 2026-09-24)
_The breakdown below reflects the original 2026-08-06 suite of 26 tests. The suite has since grown: `tests/` now holds `test_aak_provider.py`, `test_benchmark.py`, and `test_host_adapter.py`._
- Compression engine (originally 8 tests)
- Tier management (originally 7 tests)
- Temporal decay (originally 5 tests)
- Context building (originally 5 tests including focus filter, truncation, overrides)
- Full pipeline integration (originally 1 test)

## Integration Approach

_Historical options from the 2026-08-06 pitch. **None is currently recommended
or authorized** — see the status banner. Reopening requires the escalation rule
in `DECISIONS.md` ADR 2026-09-24 to fire and a substantive source review to
record GO._

### Option A: Standalone Provider Package (originally Recommended; not now)
Publish `aaak-provider` to PyPI. hermes-lcm users install optionally:
```bash
pip install aaak-provider
```

hermes-lcm detects and uses it via provider registry pattern.

### Option B: Built-in Provider
Copy `aaak_provider/` into `hermes-lcm/providers/aaak/` and register in plugin system.

### Option C: Config-Driven Plugin
Extend hermes-lcm's CompressionPlugin interface (like Mnemosyne's) to support multiple backends including AAAK.

## Proposed Config Schema (for Option C)

```yaml
# ~/.config/hermes/hermes-lcm/config.yaml
lcm:
  compression:
    provider: "aaak"  # or "caveman", "llm", "none"
    aaak:
      abbreviation_map_path: "~/.config/hermes/hermes-lcm/aaak_abbrev.json"
      tier_budgets:
        identity: 50
        critical: 120
        recent: 300
        nightstand: 200
        deep: null
      lambda_rate: 0.05
      nightstand_enabled: true
      nightstand_min_tokens: 800
      rolling_summary_enabled: true
```

## Files Ready for Contribution

```
/home/hermes-pi/projects/hermes-lcm-aak-contribution/
├── pyproject.toml          # Package config
├── README.md               # Documentation
├── aaak_provider/
│   ├── __init__.py
│   ├── compression.py      # AAAK engine
│   ├── tier_manager.py     # 4-layer tiers + rolling summaries
│   ├── temporal_decay.py   # Exponential decay
│   ├── context_builder.py  # ContextBlock builder
│   ├── benchmark.py        # Benchmark harness
│   └── host_adapter.py     # Hermes host adapter
├── scripts/
│   ├── verify.sh           # Project gate (tests + benchmark + controls)
│   ├── benchmark_aak.py    # Corpus benchmark
│   ├── benchmark_scale.py  # Sequential scaling / latency
│   └── host_smoke.py       # Host smoke check
└── tests/
    ├── test_aak_provider.py
    ├── test_benchmark.py
    └── test_host_adapter.py  # 106 passing, 1 skipped (2026-09-24)
```

## Validation

Run the project's own gate (it also enforces the benchmark and
structural-fidelity checks):
```bash
$ ./scripts/verify.sh
...
[2/4] Test suite
106 passed, 1 skipped
...
[3/4] Benchmark and structural-fidelity gate
benchmark: PASS (heuristic aggregate ratio=1.0941)
...
[4/4] Tracked project controls
verification: PASS
```

## Compatibility

- Python ≥3.11
- Zero dependencies (stdlib only)
- Apache-2.0 license (compatible with hermes-lcm)
- No Rust/PyO3/build toolchain required

## Questions for Maintainer

_Historical only — not addressed to hermes-lcm. Recorded so the dorm decision
can be revisited if the escalation rule ever fires._

1. **Preferred integration path** — Option A/B/C above?
2. **Provider registry** — Does hermes-lcm have or plan a provider registry for compression backends?
3. **Config location** — Where should AAAK config live? (hermes-lcm config, separate file, env vars)
4. **Rolling summaries storage** — Should these persist in hermes-lcm DB (new node type) or externalized payloads?
5. **Nightstand tier** — Is a new tier for auto-writes desirable, or should this map to existing episodic/working?

## Next Steps

**None authorized (2026-09-24).** The steps below are the original 2026-08-06
proposal, retained for history only. No PR, no PyPI publication, and no
integration work is in flight. Reopening requires the escalation rule in
`DECISIONS.md` ADR 2026-09-24 to fire *and* a substantive source review to
record GO.

_If that gate ever fires, the original plan was:_
1. Open a PR with the provider code
2. Or publish to PyPI and document integration
3. Collaborate on config schema and storage integration

## References

- Lumina source: https://github.com/Bino5150/lumina (Apache-2.0)
- Wiki (verified present): `~/wiki/entities/lumina/mempalace-aak-research.md`
- ~~Full research: `~/.hermes/projects/lumina-mempalace-research/README.md`~~ — path no longer exists (verified 2026-09-28)
- ~~Mnemosyne CompressionPlugin prior art: `~/.hermes/skills/development/mnemosyne-compression-plugin/`~~ — path no longer exists (verified 2026-09-28); `~/.hermes/skills/development/` does not exist

---

**Author:** Hermes Agent (on behalf of user)  
**Date:** 2026-08-06  
**License:** Apache-2.0