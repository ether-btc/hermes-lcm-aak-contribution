#!/usr/bin/env python3
"""Run the AAAK baseline benchmark and emit JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Permit running this file directly from a source checkout.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aaak_provider.benchmark import dump_report, run_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    parser.add_argument("--output", type=Path, help="write JSON to this path instead of stdout")
    parser.add_argument(
        "--tokenizer",
        choices=("heuristic", "tiktoken-cl100k"),
        default="heuristic",
        help="token measurement backend; tiktoken is optional and never auto-loaded",
    )
    parser.add_argument(
        "--latency-iterations",
        type=int,
        default=0,
        help="optional timed compression samples per case (0 disables wall-clock data)",
    )
    args = parser.parse_args()

    kwargs = {}
    if args.tokenizer == "tiktoken-cl100k":
        try:
            import tiktoken
        except ImportError:
            parser.error(
                "--tokenizer tiktoken-cl100k requires optional dependency tiktoken"
            )
        encoder = tiktoken.get_encoding("cl100k_base")
        kwargs = {
            "token_counter": lambda text: len(encoder.encode(text)),
            "token_measurement": "tiktoken:cl100k_base",
        }

    kwargs["latency_iterations"] = args.latency_iterations
    report = dump_report(run_benchmark(**kwargs), pretty=args.pretty)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
