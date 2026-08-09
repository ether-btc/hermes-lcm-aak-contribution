# PRAXIS Record — AAAK Provider

## Classification

**Problem type:** EXTEND + ANALYZE. The package exists and is functional, but its integration contract, evidence, and project controls are incomplete.

**Objective:** Establish whether AAAK should remain a standalone deterministic compressor, become an optional hermes-lcm provider, or be absorbed into an upstream context-engine interface. Make the smallest reversible changes that produce an integration-ready project without claiming runtime integration prematurely.

## Constraint envelope

- **Time:** No external deadline specified; use risk-first sequencing.
- **Scope:** This repository, its roadmap, tests, package contract, and integration research.
- **Resources:** Python 3.11+, stdlib runtime, pytest, local hermes-lcm checkout, upstream GitHub sources.
- **Quality:** Production-oriented correctness for a deterministic compression library; no unmeasured "30x" or recall claims.
- **Dependencies:** hermes-lcm's actual compaction/context contracts; Hermes Agent's context-engine plugin seam; Lumina source attribution.
- **Out of scope:** Activating AAAK in the live Hermes installation, changing hermes-lcm, opening upstream PRs, or publishing to PyPI.

## Frameworks

- **Separation of concerns:** Keep compression, tier policy, storage, and host integration independently testable.
- **Measurement-first:** Replace headline compression claims with reproducible token, latency, and fidelity measurements.
- **Reversibility test:** Prototype the adapter before choosing package adoption, built-in copy, or a durable host API.
- **MECE/inversion:** Audit algorithm correctness, package quality, integration contract, evaluation, operations, and governance separately; test how the project could fail.

## Current evidence

- The package is standalone and the hermes-lcm checkout contains no AAAK implementation.
- The package's direct test command now works from a checkout and passes 56 tests.
- The original roadmap offered three integration options but did not establish a decision gate, compatibility contract, benchmark gate, rollback behavior, or owner/exit criteria.
- Lumina's source architecture separates compressed closets from verbatim drawers and uses L0/L1/L2/L3 layering; AAAK should preserve that conceptual split rather than replace hermes-lcm's lossless source lineage.

## Decision gates

1. **Algorithm gate:** deterministic output, safe token-boundary substitutions, configurable fillers, valid decay parameters, and property tests.
2. **Evidence gate:** reproducible corpus with exact tokenizer choice, reduction distribution, latency, and semantic/fidelity checks.
3. **Adapter gate:** a narrow hermes-lcm-compatible adapter can round-trip metadata and preserve source references without changing the host database schema.
4. **Canary gate:** opt-in deployment demonstrates no regression in recall, tool-call continuity, or budget convergence, with a one-switch rollback.

No gate permits claiming AAAK is integrated until the corresponding test evidence exists.
