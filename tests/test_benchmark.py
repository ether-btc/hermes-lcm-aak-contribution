"""Tests for the deterministic AAAK benchmark contract."""

import json

from aaak_provider.benchmark import BenchmarkCase, dump_report, run_benchmark
from aaak_provider.compression import AAkCompressor


def test_benchmark_report_is_deterministic_and_labels_heuristic_tokens():
    cases = (BenchmarkCase("sample", "The user prefers dark mode", label="PREF"),)
    first = run_benchmark(cases)
    second = run_benchmark(cases)

    assert first == second
    assert first["token_measurement"] == "heuristic: max(1, len(text) // 4)"
    assert json.loads(dump_report(first))["schema_version"] == 3
    assert len(first["corpus_sha256"]) == 64


def test_benchmark_reports_structural_literal_preservation():
    case = BenchmarkCase(
        "path",
        "Read /home/hermes-pi/memory/database.txt",
        protected_literals=("/home/hermes-pi/memory/database.txt",),
    )

    report = run_benchmark((case,))

    assert report["structural_fidelity_pass"] is True
    assert report["semantic_probe_pass"] is True
    assert report["deterministic_output_pass"] is True
    assert report["cases"][0]["missing_protected_literals"] == []


def test_compressor_preserves_urls_paths_and_inline_code():
    compressor = AAkCompressor()
    text = (
        "Read /home/hermes-pi/memory/database.txt, call "
        "https://example.com/database?mode=dark, and keep `database_connection`."
    )

    result = compressor.compress(text)

    assert "/home/hermes-pi/memory/database.txt" in result
    assert "https://example.com/database?mode=dark" in result
    assert "`database_connection`" in result


def test_benchmark_accepts_explicit_token_counter():
    case = BenchmarkCase("custom", "abcdef", protected_literals=("abcdef",))

    report = run_benchmark(
        (case,),
        token_counter=lambda text: len(text),
        token_measurement="test-character-counter",
    )

    assert report["token_measurement"] == "test-character-counter"
    assert report["total_input_tokens"] == 6
    assert report["token_count_kind"] == "custom"
    assert report["structural_fidelity_pass"] is True


def test_benchmark_reports_missing_semantic_probe_separately():
    case = BenchmarkCase(
        "semantic-probe",
        "The user prefers dark mode",
        semantic_requirements=("PREF:", "must-not-exist"),
        label="PREF",
    )

    report = run_benchmark((case,))

    assert report["structural_fidelity_pass"] is True
    assert report["semantic_probe_pass"] is False
    assert report["cases"][0]["missing_semantic_requirements"] == ["must-not-exist"]


def test_benchmark_rejects_invalid_token_counter_result():
    case = BenchmarkCase("invalid", "abcdef")

    try:
        run_benchmark((case,), token_counter=lambda text: -1)
    except ValueError as exc:
        assert "non-negative integer" in str(exc)
    else:
        raise AssertionError("invalid token counter result was accepted")


def test_benchmark_latency_is_explicit_and_reports_percentiles():
    report = run_benchmark((BenchmarkCase("latency", "Project is running"),), latency_iterations=5)

    assert report["latency_iterations"] == 5
    assert report["latency_clock"] == "time.perf_counter_ns"
    assert report["latency_p50_us"] > 0
    assert report["latency_p95_us"] >= report["latency_p50_us"]
    assert report["cases"][0]["latency_p95_us"] >= report["cases"][0]["latency_p50_us"]


def test_default_corpus_has_structural_fidelity_across_input_classes():
    report = run_benchmark()

    assert report["corpus_size"] >= 8
    assert report["structural_fidelity_pass"] is True
    assert report["semantic_probe_pass"] is True
    assert report["deterministic_output_pass"] is True
    assert all(case["missing_protected_literals"] == [] for case in report["cases"])
    assert report["cases"][4]["structure_failure"] is None


def test_compressor_preserves_json_string_literals():
    result = AAkCompressor().compress(
        '{"project": "hermes-lcm", "enabled": false}'
    )

    assert '"project"' in result
    assert '"hermes-lcm"' in result
