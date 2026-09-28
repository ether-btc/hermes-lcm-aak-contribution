# AAAK Roadmap

## Verdict-driving target

Make AAAK an **optional, standalone deterministic compression provider with a narrow adapter seam**, not a replacement for hermes-lcm's lossless store/DAG. The package must prove compression and fidelity first, then integrate through an explicit adapter and opt-in canary.

> **2026-09-24 — FROZEN / DEFER dorm (supersedes all milestones below).** The aggregate cl100k ratio is 0.9729x with only one of nine corpus cases compressing, and two independent reviewers concluded **reviews found no safe contract-preserving tokenizer-aware implementation without an explicit label/context contract decision**. AAAK remains a standalone reference; see [[STATUS]] `Decision — 2026-09-24 (DEFER / dorm)` and DECISIONS ADR.

## Milestone 0 — Evidence and contract (highest risk first)

**Demonstrable state:** A fresh checkout can run the package and produce a benchmark report whose claims are reproducible.

- [x] Define the public API and versioning policy (`AAkCompressor`, `ContextBuilder`, tier objects, result metadata).
- [x] Add a benchmark corpus: prose, tool output, JSON/log-like text, identifiers, dates, URLs, code, multilingual/Unicode samples.
- [x] Measure exact tokenizer counts when available and report the fallback estimator separately.
- [x] Report median/p95 compression ratio and latency, not a single "~30x" number.
- [x] Add fidelity probes: protected literals, identifiers, URLs, numbers, negation, dates, and label stability.
- [x] Add property tests for idempotence policy, word-boundary safety, malformed maps, empty input, and timestamp edge cases.

**Exit:** `python3 scripts/benchmark_aak.py --pretty` emits versioned JSON with corpus hash, tokenizer-measurement metadata, ratio distribution, and pass/fail structural-fidelity checks.

## Milestone 1 — Package correctness and operability

**Demonstrable state:** The package behaves predictably as an installed artifact and rejects unsafe configuration.

- [x] Run a publish/import smoke test in an isolated environment (`scripts/host_smoke.py`; hermes-agent plugin-discovery loader, opt-in and exits 0 when hermes-agent is absent).
- [ ] ~~and wheel build check~~ — **not implemented; this box was checked in error.** Verified 2026-09-28: no `bdist`/`python -m build`/wheel invocation exists in any script, test, or `verify.sh` step, and no isolated-venv install test is present in `tests/`. A wheel-build gate remains **open** and must not be re-checked without adding one.
- [x] Validate abbreviation-map schema: string-to-string entries, non-empty keys, deterministic ordering, and collision warnings.
- [x] Decide whether custom filler words replace or extend defaults; document and test the choice.
- [x] Add explicit timestamp policy (UTC-aware timestamps preferred; invalid/future timestamps handled deterministically).
- [x] Bound or compact rolling summaries; current append-only behavior can exceed the stated tier budget.
- [x] Replace ambiguous "L0-L3" language with the actual five internal categories (`identity`, `critical`, `recent`, `nightstand`, `deep`).
- [x] Add package metadata checks (`pyproject.toml`: name, version, `requires-python >=3.11`, `license = "Apache-2.0"`, dev/benchmark extras).
- [ ] ~~Reconcile the two package version numbers~~ — **the versions disagree, and the package-level metadata check does not catch it.** Verified 2026-09-28: `pyproject.toml` declares `version = "1.0.0"` while `aaak_provider/__init__.py:54` declares `__version__ = "1.1.0"`. The "package metadata checks" box above is therefore narrower than its wording suggests — it does not cross-check the two sources. Reconciling them (and adding a test that would fail if they diverge again) is **open**; which value is authoritative is a maintainer decision, deliberately not made here while the project is in DEFER dorm.
- [ ] ~~Add license file, changelog, supported-Python CI matrix~~ — **never done; this checkbox was checked in error on 2026-08-15.** Verified 2026-09-28: the repo contains **no `LICENSE` (or COPYING) file, no `CHANGELOG`, and no `.github/workflows/` directory**, and `git log --all -- LICENSE CHANGELOG.md` returns nothing. The license is declared only as a `pyproject.toml` metadata field, which is not the same as shipping the license text. All three remain **open**; they are deliberately NOT done while the project is in DEFER dorm (2026-09-24), and must not be re-checked without producing the artifacts.

**Exit:** wheel installs into a clean venv; all tests run without `PYTHONPATH`; CI covers supported Python versions; budget and configuration invariants are tested. _Status verified 2026-09-28: the invariant/configuration portion is met and `verify.sh` runs the suite with no `PYTHONPATH` set; the wheel-install and CI-matrix portions are **unmet** and are now tracked as open items above._

## Milestone 1.5 — Compression ratio recovery (M2.5) — ⚠️ IMPLEMENTED, EXIT NOT MET (marked "✅ COMPLETE" in error on 2026-08-15)

**Demonstrable state (as claimed 2026-08-15):** "AAAK no longer expands context under `cl100k_base`."
**Actual demonstrable state (verified 2026-09-24):** AAAK **still expands** under `cl100k_base` — 0.9729x aggregate (215 input -> 221 output tokens). The mechanisms below were genuinely built and are real (verified 2026-09-28: 54 of 83 default abbreviations are multi-word phrases; `_is_structured` content-type skipping exists at `compression.py:280`; the `expansion_guard` field exists at `compression.py:142`), but they did not deliver the milestone's stated outcome.

- [x] Identify root cause: single-word abbreviation map (1:1 token swaps), no expansion guard, overlapping regex matches, no content-type awareness.
- [x] Add multi-word phrase abbreviations ("the user prefers" → "") for net-positive compression.
- [x] Add expansion guard: return original if `counter(result) > counter(text)`.
- [x] Add content-type classifier: skip compression on JSON/code/URLs/logs.
- [x] Fix regex overlap with single-pass alternation and deduplication.
- [x] Update benchmark to reflect new ratio metrics.

**Exit (as stated 2026-08-15):** `cl100k_base` benchmark ratio >= 0.95x on the original corpus; >1.0x on realistic long-form prose.
**Exit status (verified 2026-09-24):** **PARTIALLY MET — and the met half does not mean success.** The ratio convention is input/output, so higher is better. The corpus floor *is* cleared: 0.9729x >= 0.95x. But the substantive half — **>1.0x on realistic long-form prose — is NOT MET**, and no such figure reproduces: per-case, only unicode-prose (1.111x) compresses, and the remaining cases are at or below 1.00x. An aggregate below 1.0x is still token *expansion*, so clearing a 0.95x floor while remaining under 1.0x means the milestone was closed on a threshold that was too low to demonstrate its own stated goal. This unmet half is the direct evidence behind the 2026-09-24 DEFER/dorm decision.

**Results:**
- Nine-case benchmark: 215 input / 221 output = 0.973x (up from 0.947x)
- Realistic long-form (>200 chars): 1.05x – 1.21x compression _(historical 2026-08-15 heuristic warm-up figures; never reproduced on the pinned `cl100k` set, and the nine-case corpus contains no >200-char case — see the Exit status above)_
- Expansion guard prevents token increase on structured content

## Milestone 2 — Integration spike, no host changes

**Demonstrable state:** A local adapter consumes hermes-lcm-shaped inputs and returns a provider-neutral compressed block while preserving source identity and fallback behavior.

- [x] Inspect and pin the actual hermes-lcm seam at the target commit; do not assume a generic `ContextBlock` is compatible.
- [x] Define an adapter protocol with input messages, output block, token accounting, source references, and truncation/fallback status.
- [x] Build a fake-host contract test suite in this repository.
- [ ] Compare AAAK against current hermes-lcm paths: local LLM summary, fallback model, and deterministic truncation.
- [ ] Keep the adapter optional and side-effect free; no database schema or runtime activation in this milestone.

**Exit:** adapter contract tests pass against fixtures and a canary harness proves a one-switch fallback to the existing host path.

## Milestone 3 — Upstream integration proposal

**Demonstrable state:** Maintainers can review a minimal integration proposal with evidence and a rollback plan.

- [ ] Choose among optional package/provider registry, built-in provider, or host adapter based on Milestone 2 evidence.
- [ ] Submit the smallest upstream change: provider registration plus config/feature flag, not tier/storage redesign.
- [ ] Specify precedence: explicit LLM summary → AAAK (if enabled) → deterministic truncation, or the maintainer-approved order.
- [ ] Specify observability: provider selected, input/output token estimates, ratio, latency, fallback reason, and source lineage.
- [ ] Specify privacy: no new network calls; redact or preserve host redaction semantics.

**Exit:** upstream review-ready patch/PR, compatibility matrix, and documented rollback switch.

## Milestone 4 — Canary and evaluation

**Demonstrable state:** AAAK can run opt-in on representative sessions with evidence that it does not silently damage recall or tool continuity.

- [ ] Run LOCOMO/LongMemEval-style recall probes where applicable, plus Hermes-specific tool-call and source-lineage fixtures.
- [ ] Compare baseline, AAAK-only, hybrid, and truncation-only modes under the same reader model and token budget.
- [ ] Track answer accuracy, abstention/contradiction behavior, token reduction, p50/p95 latency, and fallback rate.
- [ ] Canary only with opt-in configuration and an immediate rollback switch.

**Exit:** decision memo: adopt, revise, or reject; no default-on change without a demonstrated quality floor.

## Explicit non-goals

- Replacing hermes-lcm's immutable raw store or summary DAG.
- Treating AAAK as lossless or as a decoder for arbitrary prose.
- Using headline compression ratio as a proxy for memory quality.
- Adding vector databases, LLM extraction, or a new persistence layer to this package before the adapter and benchmark gates pass.
