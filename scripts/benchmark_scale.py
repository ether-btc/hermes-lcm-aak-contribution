#!/usr/bin/env python3
"""Measure sequential AAAK latency across corpus sizes.

This is an opt-in, host-local evidence tool. It deliberately does not report a
portable performance claim and does not mix wall-clock data into the
reproducible structural benchmark.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aaak_provider.benchmark import DEFAULT_CORPUS  # noqa: E402
from aaak_provider.compression import AAkCompressor  # noqa: E402


def percentile(values: list[int], percentile_value: float) -> int:
    rank = max(1, math.ceil(len(values) * percentile_value / 100))
    return sorted(values)[rank - 1]


def measure(size: int, repeats: int, compressor: AAkCompressor) -> dict:
    cases = tuple(DEFAULT_CORPUS[index % len(DEFAULT_CORPUS)] for index in range(size))
    for case in cases:
        compressor.compress(case.text, case.label)

    samples_ns: list[int] = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        for case in cases:
            compressor.compress(case.text, case.label)
        samples_ns.append(time.perf_counter_ns() - started)

    return {
        "case_count": size,
        "repeats": repeats,
        "total_p50_us": round(percentile(samples_ns, 50) / 1_000, 3),
        "total_p95_us": round(percentile(samples_ns, 95) / 1_000, 3),
        "per_case_p50_us": round(percentile(samples_ns, 50) / size / 1_000, 3),
        "per_case_p95_us": round(percentile(samples_ns, 95) / size / 1_000, 3),
        "total_mean_us": round(statistics.mean(samples_ns) / 1_000, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 9, 90])
    args = parser.parse_args()
    if args.repeats <= 0 or any(size <= 0 for size in args.sizes):
        parser.error("--repeats and --sizes values must be positive")

    report = {
        "schema_version": 1,
        "measurement": "sequential compression wall-clock scaling",
        "clock": "time.perf_counter_ns",
        "warmup": "one full corpus pass per size",
        "percentile": "nearest-rank p50/p95",
        "units": "microseconds",
        "disclaimer": "single-host, single-process observations; not portable guarantees",
        "sizes": [measure(size, args.repeats, AAkCompressor()) for size in args.sizes],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
