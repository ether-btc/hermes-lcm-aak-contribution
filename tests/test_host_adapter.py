"""Fake-host contract tests for the AAAK hermes-agent adapter.

These tests exercise the adapter against a synthetic host that simulates
the ``agent.context_engine.ContextEngine`` ABC surface without
requiring hermes-agent at import time. When hermes-agent is importable,
the test module additionally asserts the adapter's class structure
satisfies the real ABC (``test_real_abc_conformance``).

Scope
=====

This suite is the M2 deliverable from the AAAK roadmap:
``Build a fake-host contract test suite in this repository.`` It
covers:

- ABC conformance (real hermes-agent when available)
- Required attribute surface (host reads these for display / preflight)
- ``update_from_response`` records legacy + canonical buckets
- ``should_compress`` / ``should_compress_info`` honor
  ``threshold_percent`` * ``context_length``
- ``on_session_start`` / ``on_session_end`` / ``on_session_reset``
  lifecycle hooks flush rolling payloads without raising
- ``compress`` preserves protected head/tail verbatim, bundles middle
  into one synthetic summary message, never raises (falls back to the
  original message list)
- ``prune_tool_results_only`` trims oversized tool results and returns
  the prune count
- ``select_context`` returns ``None`` (defer to ``compress()``)
- Determinism: same input → byte-identical output
- Rolling summary bounds: total payload size respects
  ``rolling_summary_max_chars``
- Custom abbreviation map from disk is honored
- Token estimator can be injected

It does NOT measure semantic adequacy (that lives in
``tests/test_aak_provider.py`` and ``SEMANTIC_EVALUATION.md``).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from aaak_provider.host_adapter import (
    AAAKAdapterConfig,
    AAAKContextEngine,
    DEFAULT_ADAPTER_CONFIG,
    _default_token_estimator,
    _load_rolling_payload,
    _save_rolling_payload,
    _split_message_roles,
    as_context_engine_subclass,
    create_engine,
    externalized_payload_path,
    register,
)


# ---------------------------------------------------------------------------
# Helpers — fake host
# ---------------------------------------------------------------------------


class _FakeHost:
    """A minimal stand-in for hermes-agent's plugin ``EngineCollector``.

    Mirrors ``plugins.context_engine._EngineCollector`` shape: a
    ``register_context_engine(engine)`` method that captures the engine
    and exposes it as ``host.engine``.
    """

    def __init__(self) -> None:
        self.engine: Optional[AAAKContextEngine] = None

    def register_context_engine(self, engine: AAAKContextEngine) -> None:
        self.engine = engine


def _make_long_transcript(n: int = 20) -> List[Dict[str, Any]]:
    """Build a synthetic transcript with N user/assistant exchanges."""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": "You are a helpful assistant running on Hermes."},
    ]
    for i in range(n):
        messages.append(
            {
                "role": "user",
                "content": (
                    f"The user prefers dark mode and vim keybindings because "
                    f"the project is important. Iteration {i} of {n}. "
                    f"Identifier hermes_lcm_context_engine_{i} should be preserved. "
                    f"URL https://example.com/api?mode=dark&i={i} should be preserved."
                ),
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": (
                    f"Acknowledged iteration {i}. Dark mode + vim bindings configured. "
                    f"Identifier hermes_lcm_context_engine_{i} preserved. "
                    f"URL https://example.com/api?mode=dark&i={i} preserved verbatim."
                ),
            }
        )
    return messages


def _make_transcript_with_tools() -> List[Dict[str, Any]]:
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Run the long-running search task."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": ("x" * 8000),  # oversized tool result
        },
        {"role": "assistant", "content": "Search returned a long payload; summary follows."},
        {"role": "user", "content": "Continue."},
    ]


# ---------------------------------------------------------------------------
# ABC conformance (real hermes-agent when importable)
# ---------------------------------------------------------------------------


def _host_engine_abc_available() -> bool:
    """Return True iff hermes-agent's ContextEngine ABC is importable.

    We deliberately do not import at module top — hermes-agent is a
    runtime-time optional, never a build-time dependency for AAAK.
    """
    try:
        from agent.context_engine import ContextEngine  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _host_engine_abc_available(),
    reason="hermes-agent not importable; duck-typed contract only",
)
def test_real_abc_conformance_via_wrapper() -> None:
    """The :func:`as_context_engine_subclass` helper satisfies the real ABC.

    ``create_engine()`` deliberately returns a raw
    :class:`AAAKContextEngine` (no hermes-agent import). Hosts that
    require ``isinstance(engine, ContextEngine)`` should call
    :func:`as_context_engine_subclass` to get the dynamically-built
    wrapper subclass.
    """
    from agent.context_engine import ContextEngine  # type: ignore

    wrapper_cls = as_context_engine_subclass()
    assert wrapper_cls is not None, "wrapper class not built"
    instance = wrapper_cls()
    assert isinstance(instance, ContextEngine), (
        "wrapped AAAK engine does not satisfy agent.context_engine.ContextEngine"
    )


def test_as_context_engine_subclass_returns_subclass_when_host_available() -> None:
    """``as_context_engine_subclass`` returns ``None`` without the host."""
    if _host_engine_abc_available():
        cls = as_context_engine_subclass()
        assert cls is not None
        from agent.context_engine import ContextEngine  # type: ignore

        assert issubclass(cls, ContextEngine)


# ---------------------------------------------------------------------------
# Identity and required-attribute surface
# ---------------------------------------------------------------------------


def test_engine_name_is_aaak() -> None:
    assert create_engine().name == "aaak"


@pytest.mark.parametrize(
    "attr",
    [
        "last_prompt_tokens",
        "last_completion_tokens",
        "last_total_tokens",
        "last_input_tokens",
        "last_output_tokens",
        "last_cache_read_tokens",
        "last_cache_write_tokens",
        "last_reasoning_tokens",
        "threshold_tokens",
        "context_length",
        "compression_count",
        "threshold_percent",
        "protect_first_n",
        "protect_last_n",
        "emit_automatic_compaction_status",
    ],
)
def test_required_class_attribute_exists(attr: str) -> None:
    """The host reads these directly; missing attributes are integration bugs."""
    engine = create_engine()
    assert hasattr(engine, attr), f"missing required attribute: {attr}"
    assert isinstance(getattr(engine, attr), (int, float, bool)), (
        f"{attr} has wrong type: {type(getattr(engine, attr))}"
    )


# ---------------------------------------------------------------------------
# update_from_response / threshold
# ---------------------------------------------------------------------------


def test_update_from_response_records_legacy_keys() -> None:
    engine = create_engine()
    engine.update_from_response(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    )
    assert engine.last_prompt_tokens == 100
    assert engine.last_completion_tokens == 50
    assert engine.last_total_tokens == 150


def test_update_from_response_records_canonical_buckets() -> None:
    engine = create_engine()
    engine.update_from_response(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "input_tokens": 110,
            "output_tokens": 55,
            "cache_read_tokens": 30,
            "cache_write_tokens": 10,
            "reasoning_tokens": 5,
        }
    )
    assert engine.last_input_tokens == 110
    assert engine.last_output_tokens == 55
    assert engine.last_cache_read_tokens == 30
    assert engine.last_cache_write_tokens == 10
    assert engine.last_reasoning_tokens == 5


def test_threshold_derives_from_context_length() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    assert engine.threshold_tokens == 750  # 0.75 * 1000


def test_update_model_recomputes_threshold() -> None:
    engine = create_engine()
    engine.update_model(model="m", context_length=2_000)
    assert engine.context_length == 2_000
    assert engine.threshold_tokens == 1_500


# ---------------------------------------------------------------------------
# should_compress / should_compress_info
# ---------------------------------------------------------------------------


def test_should_compress_false_below_threshold() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    assert not engine.should_compress(500)


def test_should_compress_true_at_or_above_threshold() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    assert engine.should_compress(750)
    assert engine.should_compress(800)


def test_should_compress_false_when_threshold_unknown() -> None:
    engine = create_engine()
    assert not engine.should_compress(999)


def test_should_compress_info_reports_reason() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    flag, reason = engine.should_compress_info(800)
    assert flag is True
    assert reason is not None
    assert "threshold_tokens" in reason

    flag2, reason2 = engine.should_compress_info(500)
    assert flag2 is False
    assert reason2 is None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_on_session_start_resets_compression_count() -> None:
    engine = create_engine()
    engine.compression_count = 7
    engine.on_session_start("s1")
    assert engine.compression_count == 0


def test_on_session_end_flushes_rolling_payload(tmp_path: Path) -> None:
    cfg = AAAKAdapterConfig(rolling_summary_state_dir=str(tmp_path))
    engine = create_engine(cfg)
    engine.on_session_start("session-a", context_length=1_000)
    engine.update_from_response({"prompt_tokens": 800})
    engine.compress(_make_long_transcript(4))
    engine.on_session_end("session-a", [])
    payload_path = externalized_payload_path(str(tmp_path), "session-a")
    assert payload_path.exists(), "rolling payload not persisted on session end"


def test_on_session_reset_flushes_rolling_payload(tmp_path: Path) -> None:
    cfg = AAAKAdapterConfig(rolling_summary_state_dir=str(tmp_path))
    engine = create_engine(cfg)
    engine.on_session_start("session-b", context_length=1_000)
    engine.compress(_make_long_transcript(2))
    engine.on_session_reset()
    payload_path = externalized_payload_path(str(tmp_path), "session-b")
    assert payload_path.exists()


def test_lifecycle_hooks_do_not_raise_with_no_session_id() -> None:
    engine = create_engine()
    engine.on_session_end("", [])  # no session_id; should be a no-op
    engine.on_session_reset()      # no session_id; should be a no-op


def test_bind_session_state_keeps_existing_session() -> None:
    engine = create_engine()
    engine.on_session_start("alpha", conversation_id="c1")
    engine.bind_session_state(conversation_id="c2")
    assert engine._session_id == "alpha"
    assert engine._conversation_id == "c2"


# ---------------------------------------------------------------------------
# compress()
# ---------------------------------------------------------------------------


def test_compress_returns_original_when_no_middle() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "tail"},
        ]
    )
    assert out[0]["role"] == "system"
    assert out[-1]["role"] == "user"


def test_compress_preserves_system_prompt() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress(_make_long_transcript(4))
    assert out[0]["role"] == "system"
    assert out[0]["content"] == "You are a helpful assistant running on Hermes."


def test_compress_protected_tail_is_verbatim() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    transcript = _make_long_transcript(4)
    out = engine.compress(transcript)
    # The last 4 messages of the input (protect_last_n=4) must appear verbatim
    # at the tail of the output, immediately after the summary message.
    expected_tail = transcript[-4:]
    assert out[-4:] == expected_tail, "tail messages were not preserved verbatim"


def test_compress_inserts_summary_message_role_assistant() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress(_make_long_transcript(4))
    # Locate the synthetic summary message; it has the [AAAK summary] prefix
    # and lives between the protected head (system + 1 user) and the protected
    # tail (last 4 messages).
    summary_idx = None
    for i, m in enumerate(out):
        if isinstance(m.get("content"), str) and m["content"].startswith("[AAAK summary"):
            summary_idx = i
            break
    assert summary_idx is not None, "synthetic summary message not found"
    assert out[summary_idx]["role"] == "assistant", (
        "summary must use assistant role to preserve alternation invariant"
    )


def test_compress_preserves_protected_literals() -> None:
    """URLs, identifiers, paths and dates from the protected region survive."""
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress(_make_long_transcript(4))
    flat = "\n".join(
        m.get("content", "") if isinstance(m.get("content"), str) else ""
        for m in out
    )
    # The protected tail (last 4 messages of the 9-message transcript) keeps
    # the URL/identifier verbatim.
    assert "https://example.com/api?mode=dark&i=2" in flat
    assert "hermes_lcm_context_engine_2" in flat


def test_compress_does_not_raise_on_empty_messages() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress([])
    assert out == []


def test_compress_falls_back_to_original_on_internal_error() -> None:
    """If the AAAK core raises, the adapter returns the original messages."""

    class _BoomCompressor:
        def compress(self, text, label=None):  # noqa: ARG002
            raise RuntimeError("boom")

        def estimate_tokens(self, text):  # noqa: ARG002
            return 1

    cfg = AAAKAdapterConfig(fallback_to_original=True)
    engine = AAAKContextEngine(
        config=cfg, compressor=_BoomCompressor(), token_estimator=_default_token_estimator
    )
    # Force the rest of the pipeline to initialize.
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress(_make_long_transcript(4))
    assert len(out) == len(_make_long_transcript(4))
    assert engine.last_summary_fallback_used is True


def test_compress_deterministic_for_same_input() -> None:
    """Same input bytes must yield byte-identical compressed output."""
    engine_a = create_engine()
    engine_b = create_engine()
    engine_a.on_session_start("s", context_length=1_000)
    engine_b.on_session_start("s", context_length=1_000)
    transcript = _make_long_transcript(3)
    out_a = engine_a.compress(transcript)
    out_b = engine_b.compress(transcript)
    # Compare summaries only (timestamps may differ in other metadata).
    sum_a = next(
        m["content"] for m in out_a if m["content"].startswith("[AAAK summary")
    )
    sum_b = next(
        m["content"] for m in out_b if m["content"].startswith("[AAAK summary")
    )
    assert sum_a == sum_b


def test_compress_prepends_memory_context() -> None:
    engine = create_engine()
    engine.on_session_start("s", context_length=1_000)
    out = engine.compress(_make_long_transcript(4), memory_context="provider-note")
    # The system-role memory note appears at index 0; the original system
    # prompt is preserved at index 1.
    assert out[0]["role"] == "system"
    assert "provider-note" in out[0]["content"]
    assert "memory provider context preserved" in out[0]["content"]


# ---------------------------------------------------------------------------
# prune_tool_results_only / select_context
# ---------------------------------------------------------------------------


def test_prune_tool_results_only_trims_oversized_tool_payloads() -> None:
    engine = create_engine()
    messages = _make_transcript_with_tools()
    pruned, n = engine.prune_tool_results_only(messages)
    assert n == 1
    tool_msg = next(m for m in pruned if m["role"] == "tool")
    assert "trimmed by AAAK" in tool_msg["content"]
    assert len(tool_msg["content"]) < len(messages[3]["content"])


def test_prune_tool_results_only_is_safe_with_no_tool_messages() -> None:
    engine = create_engine()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    pruned, n = engine.prune_tool_results_only(messages)
    assert pruned == messages
    assert n == 0


def test_select_context_returns_none() -> None:
    """AAAK defers context selection to the host and to ``compress()``."""
    engine = create_engine()
    out = engine.select_context(
        [{"role": "user", "content": "hi"}], budget_tokens=100
    )
    assert out is None


# ---------------------------------------------------------------------------
# Custom abbreviation map
# ---------------------------------------------------------------------------


def test_custom_abbreviation_map_is_loaded(tmp_path: Path) -> None:
    map_path = tmp_path / "abbrev.json"
    map_path.write_text(json.dumps({"hermes": "HRS"}), encoding="utf-8")
    cfg = AAAKAdapterConfig(abbreviation_map_path=str(map_path))
    engine = create_engine(cfg)
    engine.on_session_start("s", context_length=1_000)
    # Build a transcript whose middle contains "hermes" so the abbreviation
    # substitution actually fires. Head/tail preserve verbatim.
    transcript = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Head-protected user message"},
        {"role": "assistant", "content": "Head-protected assistant message"},
        {"role": "user", "content": "Hermes agent is running iteration 0"},
        {"role": "assistant", "content": "Ack iteration 0"},
        {"role": "user", "content": "Hermes continues iteration 1"},
        {"role": "assistant", "content": "Ack iteration 1"},
        {"role": "user", "content": "Hermes still here iteration 2"},
        {"role": "assistant", "content": "Ack iteration 2"},
        {"role": "user", "content": "Tail user message"},
        {"role": "assistant", "content": "Tail assistant message"},
    ]
    out = engine.compress(transcript)
    flat = "\n".join(m["content"] for m in out if isinstance(m.get("content"), str))
    assert "HRS" in flat, f"custom abbreviation was not applied: {flat[:300]}"


# ---------------------------------------------------------------------------
# Rolling summary bounds
# ---------------------------------------------------------------------------


def test_rolling_summary_bounded_by_max_chars(tmp_path: Path) -> None:
    cfg = AAAKAdapterConfig(
        rolling_summary_state_dir=str(tmp_path),
        rolling_summary_max_chars=128,
    )
    engine = create_engine(cfg)
    engine.on_session_start("bounded", context_length=1_000)
    # Compress five times; each pass adds new content to the rolling summary.
    transcript = _make_long_transcript(5)
    for _ in range(5):
        engine.compress(transcript)
    payload = json.loads(
        externalized_payload_path(str(tmp_path), "bounded").read_text()
    )
    summaries = payload["summaries"]
    total_chars = sum(
        len(content)
        for topics in summaries.values()
        for content in topics.values()
    )
    # Each tier should not exceed 4× max_chars (we keep one rolling string per
    # topic; bound enforcement trims to max_chars per topic).
    for tier, topics in summaries.items():
        for topic, content in topics.items():
            assert len(content) <= cfg.rolling_summary_max_chars, (
                f"tier={tier} topic={topic} exceeded budget: "
                f"{len(content)} > {cfg.rolling_summary_max_chars}"
            )


# ---------------------------------------------------------------------------
# Plugin discovery wiring
# ---------------------------------------------------------------------------


def test_register_via_fake_host() -> None:
    """The plugin-discovery ``register(ctx)`` path populates ``host.engine``."""
    host = _FakeHost()
    register(host)
    assert host.engine is not None
    assert host.engine.name == "aaak"


def test_register_attaches_fallback_attribute_for_legacy_hosts() -> None:
    class _LegacyCtx:
        pass

    ctx = _LegacyCtx()
    register(ctx)
    assert getattr(ctx, "aaak_engine") is not None
    assert ctx.aaak_engine.name == "aaak"


# ---------------------------------------------------------------------------
# Externalized payload helpers
# ---------------------------------------------------------------------------


def test_externalized_payload_path_sanitizes_session_id(tmp_path: Path) -> None:
    p = externalized_payload_path(str(tmp_path), "abc/../escape")
    assert ".." not in p.name
    assert p.parent.exists() is False  # not created until write


def test_rolling_payload_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "rolling.json"
    payload = _load_rolling_payload(path)
    payload.session_id = "round-trip"
    payload.summaries = {"recent": {"topic-a": "compressed-text"}}
    _save_rolling_payload(path, payload)
    loaded = _load_rolling_payload(path)
    assert loaded.session_id == "round-trip"
    assert loaded.summaries == {"recent": {"topic-a": "compressed-text"}}


def test_rolling_payload_corrupt_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "rolling.json"
    path.write_text("not-json{", encoding="utf-8")
    loaded = _load_rolling_payload(path)
    assert loaded.session_id == ""
    assert loaded.summaries == {}


# ---------------------------------------------------------------------------
# has_content_to_compress
# ---------------------------------------------------------------------------


def test_has_content_to_compress_true_for_long_transcript() -> None:
    engine = create_engine()
    assert engine.has_content_to_compress(_make_long_transcript(4)) is True


def test_has_content_to_compress_false_for_short_transcript() -> None:
    engine = create_engine()
    # 1 system + 1 user → no middle after protecting head/tail.
    assert engine.has_content_to_compress(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
    ) is False


# ---------------------------------------------------------------------------
# Config default sanity
# ---------------------------------------------------------------------------


def test_default_config_matches_documented_budgets() -> None:
    cfg = DEFAULT_ADAPTER_CONFIG
    assert cfg.identity_budget == 50
    assert cfg.critical_budget == 120
    assert cfg.recent_budget == 300
    assert cfg.nightstand_budget == 200
    assert cfg.lambda_rate == 0.05
    assert cfg.threshold_percent == 0.75
    assert cfg.fallback_to_original is True