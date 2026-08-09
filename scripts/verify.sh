#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '%s\n' '[1/4] Python compilation'
python3 -m compileall -q aaak_provider tests

printf '%s\n' '[2/4] Test suite'
pytest -q

printf '%s\n' '[3/4] Benchmark and structural-fidelity gate'
REPORT="$(mktemp)"
trap 'rm -f "$REPORT"' EXIT
python3 scripts/benchmark_aak.py --output "$REPORT"
python3 - "$REPORT" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    report = json.load(handle)

if not report["structural_fidelity_pass"]:
    raise SystemExit("benchmark structural-fidelity gate failed")
print(
    "benchmark: PASS "
    f"({report['token_count_kind']} aggregate ratio={report['aggregate_ratio']})"
)
PY

printf '%s\n' '[4/4] Tracked project controls'
for file in PRAXIS.md ROADMAP.md DECISIONS.md STATUS.md SEMANTIC_EVALUATION.md README.md pyproject.toml; do
  test -f "$file"
done

git diff --check
printf '%s\n' 'verification: PASS'
