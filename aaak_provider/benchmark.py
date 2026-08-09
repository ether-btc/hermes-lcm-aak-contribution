"""Reproducible AAAK benchmark and deterministic fidelity checks.

The default run uses only the package's heuristic token estimator. An exact
model-tokenizer counter can be injected explicitly; no heavyweight dependency
or network access is acquired implicitly. Protected-literal and semantic
invariant checks are deterministic probes, not full semantic-quality claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from .compression import AAkCompressor


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    text: str
    protected_literals: tuple[str, ...] = ()
    semantic_requirements: tuple[str, ...] = ()
    label: str | None = None
    structure: str | None = None


DEFAULT_CORPUS: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        name="prose-preference",
        text="The user prefers dark mode and vim keybindings because the project is important.",
        semantic_requirements=("PREF:", "dark-mode", "vim-bindings"),
        label="PREF",
    ),
    BenchmarkCase(
        name="tool-output",
        text=(
            "The local database completed the migration. "
            "Read /home/hermes-pi/projects/hermes-lcm/README.md and continue the session."
        ),
        protected_literals=("/home/hermes-pi/projects/hermes-lcm/README.md",),
        semantic_requirements=("TOOL:", "migration", "continue"),
        label="TOOL",
    ),
    BenchmarkCase(
        name="structured-literals",
        text=(
            "Use https://example.com/api?mode=dark, commit 8570827, and "
            "preserve identifier hermes_lcm_context_engine."
        ),
        protected_literals=(
            "https://example.com/api?mode=dark",
            "8570827",
            "hermes_lcm_context_engine",
        ),
        semantic_requirements=("FACT:", "preserve identifier"),
        label="FACT",
    ),
    BenchmarkCase(
        name="code-and-negation",
        text="Do not rewrite `database_connection` or the value 30x inside this code comment.",
        protected_literals=("database_connection", "30x"),
        semantic_requirements=("CODE:", "Do not rewrite"),
        label="CODE",
    ),
    BenchmarkCase(
        name="json-config",
        text='{"project": "hermes-lcm", "enabled": false, "retry_count": 3}',
        protected_literals=("project", "hermes-lcm", "retry_count", "3"),
        semantic_requirements=("\"enabled\": false",),
        structure="json",
    ),
    BenchmarkCase(
        name="shell-command",
        text="Run python3 -m pytest -q --maxfail=1 from /tmp/aak-check and keep exit code 2.",
        protected_literals=("python3 -m pytest -q --maxfail=1", "/tmp/aak-check", "2"),
        semantic_requirements=("CMD:", "exit code 2"),
        label="CMD",
    ),
    BenchmarkCase(
        name="date-and-number",
        text="The migration deadline is 2026-08-31 at 09:30 UTC; do not round 0.05 or 22%.",
        protected_literals=("2026-08-31", "09:30", "0.05", "22%"),
        semantic_requirements=("DATE:", "deadline", "do not round"),
        label="DATE",
    ),
    BenchmarkCase(
        name="unicode-prose",
        text="The user prefers café mode; preserve 日本語 and the emoji ✅ while trimming filler.",
        protected_literals=("café", "日本語", "✅"),
        semantic_requirements=("NOTE:", "preserve", "trimming filler"),
        label="NOTE",
    ),
    BenchmarkCase(
        name="log-line",
        text="2026-08-09T12:34:56Z level=ERROR request_id=req_7f3f status=500 path=/v1/memory",
        protected_literals=(
            "2026-08-09T12:34:56Z",
            "request_id=req_7f3f",
            "500",
            "/v1/memory",
        ),
        semantic_requirements=("LOG:", "level=ERROR", "status=500"),
        label="LOG",
    ),
)


def _ratio(before: int, after: int) -> float:
    return round(before / max(after, 1), 4)


def _validated_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("token counter must return a non-negative integer")
    return value


def _corpus_sha256(cases: tuple[BenchmarkCase, ...]) -> str:
    payload = json.dumps([asdict(case) for case in cases], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _percentile(values: list[int], percentile: float) -> int:
    """Nearest-rank percentile for positive wall-clock samples."""
    if not values:
        raise ValueError("cannot calculate a percentile without samples")
    rank = max(1, math.ceil(len(values) * percentile / 100))
    return sorted(values)[rank - 1]


def run_benchmark(
    cases: Iterable[BenchmarkCase] = DEFAULT_CORPUS,
    compressor: AAkCompressor | None = None,
    token_counter: Callable[[str], int] | None = None,
    token_measurement: str | None = None,
    latency_iterations: int = 0,
) -> dict:
    """Run compression and structural-literal checks.

    ``token_counter`` is an explicit seam for a target-model tokenizer. The
    default remains the package's heuristic estimator so standalone runs do
    not acquire a network or heavyweight dependency implicitly.
    """
    if isinstance(latency_iterations, bool) or not isinstance(latency_iterations, int):
        raise TypeError("latency_iterations must be an integer")
    if latency_iterations < 0:
        raise ValueError("latency_iterations must be non-negative")
    compressor = compressor or AAkCompressor()
    cases = tuple(cases)
    counter = token_counter or compressor.estimate_tokens
    measurement = token_measurement or (
        "heuristic: max(1, len(text) // 4)"
        if token_counter is None
        else "custom"
    )
    results = []
    for case in cases:
        compressed = compressor.compress(case.text, case.label)
        repeated_compressed = compressor.compress(case.text, case.label)
        latency_samples = []
        if latency_iterations:
            compressor.compress(case.text, case.label)  # warm-up outside samples
            for _ in range(latency_iterations):
                started = time.perf_counter_ns()
                compressor.compress(case.text, case.label)
                latency_samples.append(time.perf_counter_ns() - started)
        before = _validated_count(counter(case.text))
        after = _validated_count(counter(compressed))
        missing = [literal for literal in case.protected_literals if literal not in compressed]
        missing_semantics = [
            requirement for requirement in case.semantic_requirements
            if requirement not in compressed
        ]
        structure_failure = None
        if case.structure == "json":
            try:
                json.loads(compressed)
            except json.JSONDecodeError as exc:
                structure_failure = f"invalid-json: {exc.msg}"
        results.append(
            {
                "name": case.name,
                "input_chars": len(case.text),
                "output_chars": len(compressed),
                "input_tokens": before,
                "output_tokens": after,
                "ratio": _ratio(before, after),
                "protected_literals": list(case.protected_literals),
                "missing_protected_literals": missing,
                "semantic_requirements": list(case.semantic_requirements),
                "missing_semantic_requirements": missing_semantics,
                "structure_failure": structure_failure,
                "structural_fidelity_pass": not missing and structure_failure is None,
                "deterministic_output_pass": compressed == repeated_compressed,
                "semantic_probe_pass": not missing_semantics,
                "latency_p50_us": round(_percentile(latency_samples, 50) / 1_000, 3)
                if latency_samples else None,
                "latency_p95_us": round(_percentile(latency_samples, 95) / 1_000, 3)
                if latency_samples else None,
                "compressed": compressed,
            }
        )

    ratios = [result["ratio"] for result in results]
    input_tokens = sum(result["input_tokens"] for result in results)
    output_tokens = sum(result["output_tokens"] for result in results)
    token_kind = "heuristic" if token_counter is None else "custom"
    report = {
        "schema_version": 3,
        "token_measurement": measurement,
        "token_count_kind": token_kind,
        "corpus_size": len(results),
        "corpus_sha256": _corpus_sha256(cases),
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "aggregate_ratio": _ratio(input_tokens, output_tokens),
        "median_case_ratio": round(statistics.median(ratios), 4) if ratios else 0.0,
        "structural_fidelity_pass": all(
            result["structural_fidelity_pass"] for result in results
        ),
        "deterministic_output_pass": all(
            result["deterministic_output_pass"] for result in results
        ),
        "semantic_probe_pass": all(result["semantic_probe_pass"] for result in results),
        "cases": results,
    }
    if latency_iterations:
        p50s = [result["latency_p50_us"] for result in results]
        p95s = [result["latency_p95_us"] for result in results]
        report.update(
            {
                "latency_iterations": latency_iterations,
                "latency_clock": "time.perf_counter_ns",
                "latency_methodology": (
                    "one warm-up compression per case; timed compression calls; "
                    "nearest-rank p50/p95; values in microseconds"
                ),
                "latency_p50_us": round(statistics.median(p50s), 3),
                "latency_p95_us": round(statistics.median(p95s), 3),
            }
        )
    return report


def dump_report(report: dict, *, pretty: bool = False) -> str:
    """Serialize a report with stable key ordering for diffs and CI artifacts."""
    return json.dumps(report, indent=2 if pretty else None, sort_keys=True) + "\n"
