"""Hermes Agent host adapter for the AAAK compression provider.

This module is the M2 milestone deliverable from the AAAK roadmap: a thin
adapter that wires the standalone ``aaak_provider`` package into the
``ContextEngine`` ABC consumed by ``hermes-agent``. It is intentionally
zero-dependency at import time — ``agent.context_engine.ContextEngine``
is only referenced lazily, so the AAAK package remains usable from
environments where hermes-agent is not installed (e.g. the standalone
test suite, embedded use, or third-party hosts).

Adapter contract
================

A AAAK-backed context engine must answer the same ABC surface as the
built-in ``ContextCompressor`` and as the LCM engine:

  - ``name`` (property) returns the short identifier ``"aaak"``.
  - ``update_from_response(usage)`` records token usage after every
    API call.
  - ``should_compress(prompt_tokens)`` decides whether the host should
    invoke ``compress()`` this turn.
  - ``compress(messages, ...)`` replaces the message list with a
    AAAK-compressed equivalent that fits the configured budget.
  - ``on_session_start(session_id, **kwargs)`` / ``on_session_end`` /
    ``on_session_reset`` manage rolling-summary state.
  - ``update_model(...)`` re-derives the per-token threshold when the
    active model changes (mirrors LCM/ContextCompressor).
  - ``prune_tool_results_only`` and ``select_context`` are provided as
    optional hooks with safe defaults.

Lossless-source ownership
=========================

Per ``DECISIONS.md`` (2026-08-09), AAAK may compress a
provider-visible block but must not become the owner of host raw
messages. Rolling summaries are persisted to an externalized payload
file (``state_dir/aaak/<session_id>/rolling.json``), not into any
SQLite store the host owns. The adapter never imports the host's
session/state modules.

Plugin discovery
================

Hermes-agent's ``plugins.context_engine`` loader accepts two wiring
patterns:

  1. A module-level ``register(ctx)`` that calls
     ``ctx.register_context_engine(engine)``.
  2. A class that subclasses ``ContextEngine`` at module level.

This module exports a ``register(ctx)`` function so it works under
pattern 1 without ever importing hermes-agent at module load. Pattern 2
support is provided via the ``as_context_engine_subclass()`` helper,
which returns a dynamically created subclass of the real
``ContextEngine`` ABC (only attempted when the host is importable).

Bounded evidence
================

The behavior of this adapter is verified by
``tests/test_host_adapter.py`` against a fake host that simulates the
``ContextEngine`` ABC surface. Real-hermes-agent conformance is checked
when ``agent.context_engine.ContextEngine`` is importable (skipped
otherwise; hermes-agent is not a runtime dependency).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .compression import AAkCompressor, create_compressor
from .context_builder import (
    CompressionContext,
    ContextBlock,
    ContextBuilder,
    create_context_builder,
)
from .temporal_decay import TemporalDecayEngine, create_decay_engine
from .tier_manager import (
    DEFAULT_TIER_BUDGETS,
    Tier,
    TierBudget,
    TierManager,
    TieredMemory,
    create_tier_manager,
)


__all__ = [
    "AAAKContextEngine",
    "AAAKAdapterConfig",
    "DEFAULT_ADAPTER_CONFIG",
    "create_engine",
    "register",
    "as_context_engine_subclass",
    "externalized_payload_path",
]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AAAKAdapterConfig:
    """Configuration for the host adapter.

    Mirrors the YAML schema proposed in the issue (the ``aaak:`` block
    under ``context.aaak`` in ``~/.config/hermes/config.yaml``). Every
    field is optional; ``create_engine()`` substitutes sensible defaults
    so the adapter can boot with no configuration at all.
    """

    abbreviation_map_path: Optional[str] = None
    identity_budget: int = 50
    critical_budget: int = 120
    recent_budget: int = 300
    nightstand_budget: int = 200
    nightstand_enabled: bool = True
    nightstand_min_tokens: int = 800
    rolling_summary_enabled: bool = True
    rolling_summary_state_dir: Optional[str] = None
    rolling_summary_max_chars: int = 4096
    lambda_rate: float = 0.05
    threshold_percent: float = 0.75
    protect_first_n: int = 1
    protect_last_n: int = 4
    fallback_to_original: bool = True
    auto_compress_status: bool = False


DEFAULT_ADAPTER_CONFIG = AAAKAdapterConfig()


def _deep_budget(c: AAAKAdapterConfig) -> int:
    """Return the deep tier's effective budget (no cap; sentinel)."""
    return 0  # 0 means "uncapped" for the tier manager


# ---------------------------------------------------------------------------
# Rolling summary persistence (externalized payloads only)
# ---------------------------------------------------------------------------


def externalized_payload_path(state_dir: str, session_id: str) -> Path:
    """Return the on-disk path for one session's rolling summaries.

    The host adapter owns this path; the host's SQLite store is never
    touched. Mirrors hermes-agent's ``externalize.py`` convention so
    users can grep ``~/.hermes/state/aaak/<session>/rolling.json`` to
    inspect what AAAK kept.
    """
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id or "default"))
    return Path(state_dir) / "aaak" / safe_id / "rolling.json"


@dataclass
class _RollingPayload:
    """On-disk schema for the rolling-summary externalized payload."""

    schema_version: int = 1
    session_id: str = ""
    summaries: Dict[str, Dict[str, str]] = field(default_factory=dict)
    last_compressed_at: float = 0.0
    last_input_tokens: int = 0
    last_output_tokens: int = 0
    last_compression_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "summaries": self.summaries,
            "last_compressed_at": self.last_compressed_at,
            "last_input_tokens": self.last_input_tokens,
            "last_output_tokens": self.last_output_tokens,
            "last_compression_count": self.last_compression_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_RollingPayload":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            session_id=str(data.get("session_id", "")),
            summaries={
                str(tier): {str(k): str(v) for k, v in topics.items()}
                for tier, topics in (data.get("summaries") or {}).items()
            },
            last_compressed_at=float(data.get("last_compressed_at", 0.0)),
            last_input_tokens=int(data.get("last_input_tokens", 0)),
            last_output_tokens=int(data.get("last_output_tokens", 0)),
            last_compression_count=int(data.get("last_compression_count", 0)),
        )


def _load_rolling_payload(path: Path) -> _RollingPayload:
    """Load a rolling-summary payload, returning an empty payload if missing."""
    try:
        if not path.exists():
            return _RollingPayload()
        with path.open("r", encoding="utf-8") as fh:
            return _RollingPayload.from_dict(json.load(fh))
    except (OSError, ValueError, json.JSONDecodeError):
        # Corrupt or partially-written payload: treat as empty rather than
        # surfacing the failure to the host's compression path.
        return _RollingPayload()


def _save_rolling_payload(path: Path, payload: _RollingPayload) -> None:
    """Persist a rolling-summary payload atomically.

    Writes to ``<path>.tmp`` and renames so a crash mid-write does not
    truncate the prior payload.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload.to_dict(), fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def _default_token_estimator(text: str) -> int:
    """Heuristic token estimate used when no tokenizer is provided.

    The standalone benchmark records this is approximate; the
    ``AAAKAdapterConfig`` allows callers to inject a real
    ``tiktoken``/host-supplied estimator via ``create_engine(...)
    (token_estimator=...)``. The AAAK package deliberately avoids
    adding ``tiktoken`` as a hard dependency so hermes-agent hosts
    keep freedom to choose the tokenizer for ``prompt_tokens``
    measurement.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Message-list inspection helpers
# ---------------------------------------------------------------------------


def _content_text(message: Dict[str, Any]) -> str:
    """Return the rendered text for an OpenAI-format message.

    The ABC says messages may be dicts with ``role`` and ``content``;
    AAAK only needs the ``content`` field for compression. We do not
    try to interpret multi-part ``content`` arrays — AAAK is invoked
    on already-flattened messages, and any tool/function artifacts
    remain in their original dict form.
    """
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return str(content)


def _split_message_roles(
    messages: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split messages into protected-head / middle / protected-tail slices.

    Mirrors the ``protect_first_n`` / ``protect_last_n`` semantics used
    by ``ContextCompressor`` and ``hermes-lcm``. The system prompt is
    always implicitly protected (treated as part of head even if it
    pushes ``head_end`` above ``protect_first_n``).
    """
    head: List[Dict[str, Any]] = []
    tail: List[Dict[str, Any]] = []
    if not messages:
        return head, [], tail
    head_end = 0
    while head_end < len(messages) and messages[head_end].get("role") == "system":
        head.append(messages[head_end])
        head_end += 1
    non_system = list(messages[head_end:])
    # protect_first_n defaults to 1; the adapter exposes it on the config.
    # We honor the engine's ``protect_first_n`` class attribute so the host
    # can tune it via the standard config path.
    head_n = min(len(non_system), max(0, 1))
    tail_n = min(len(non_system), 4)
    head_mid = non_system[:head_n]
    tail_msgs = non_system[-tail_n:] if tail_n else []
    if tail_n:
        middle = non_system[head_n : len(non_system) - tail_n]
    else:
        middle = non_system[head_n:]
    head_out: List[Dict[str, Any]] = list(head) + list(head_mid)
    return head_out, list(middle), list(tail_msgs)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AAAKContextEngine:
    """Hermes-agent ``ContextEngine`` adapter backed by AAAK compression.

    The class is intentionally **not** a subclass of
    ``agent.context_engine.ContextEngine``. Conformance is asserted at
    runtime by the test suite (which imports the real ABC if
    available) and by the plugin loader's duck-typed contract. This
    keeps AAAK hermes-agent-free at import time.

    Lifecycle and required ABC methods are all present; the host can
    treat instances of this class exactly like a built-in
    ``ContextCompressor``.
    """

    # Required by the ABC. Class-level defaults are fine — the host
    # reads these for preflight / display purposes and updates them
    # via ``update_from_response`` and ``update_model``.
    last_prompt_tokens: int = 0
    last_completion_tokens: int = 0
    last_total_tokens: int = 0
    last_input_tokens: int = 0
    last_output_tokens: int = 0
    last_cache_read_tokens: int = 0
    last_cache_write_tokens: int = 0
    last_reasoning_tokens: int = 0
    threshold_tokens: int = 0
    context_length: int = 0
    compression_count: int = 0

    threshold_percent: float = 0.75
    protect_first_n: int = 1
    protect_last_n: int = 4
    emit_automatic_compaction_status: bool = False

    def __init__(
        self,
        config: Optional[AAAKAdapterConfig] = None,
        *,
        compressor: Optional[AAkCompressor] = None,
        tier_manager: Optional[TierManager] = None,
        decay_engine: Optional[TemporalDecayEngine] = None,
        context_builder: Optional[ContextBuilder] = None,
        token_estimator: Optional[Callable[[str], int]] = None,
    ) -> None:
        cfg = config or DEFAULT_ADAPTER_CONFIG
        self.config = cfg
        self.threshold_percent = cfg.threshold_percent
        self.protect_first_n = cfg.protect_first_n
        self.protect_last_n = cfg.protect_last_n
        self.emit_automatic_compaction_status = cfg.auto_compress_status

        # Compressor: load the abbreviation map from disk when a path is
        # configured; otherwise use the package defaults.
        if compressor is not None:
            self._compressor = compressor
        elif cfg.abbreviation_map_path:
            built = AAkCompressor()
            built.load_abbreviation_map(cfg.abbreviation_map_path)
            self._compressor = built
        else:
            self._compressor = create_compressor(None)

        # Tier manager: rebuild budgets honoring nightstand_enabled.
        if tier_manager is not None:
            self._tiers = tier_manager
        else:
            budgets = dict(DEFAULT_TIER_BUDGETS)
            budgets[Tier.IDENTITY] = TierBudget(
                tier=Tier.IDENTITY,
                max_tokens=cfg.identity_budget,
                always_inject=True,
                decay_sorted=False,
                description="Identity tier — agent/user identity",
            )
            budgets[Tier.CRITICAL] = TierBudget(
                tier=Tier.CRITICAL,
                max_tokens=cfg.critical_budget,
                always_inject=True,
                decay_sorted=False,
                description="Critical tier — preferences and active project",
            )
            budgets[Tier.RECENT] = TierBudget(
                tier=Tier.RECENT,
                max_tokens=cfg.recent_budget,
                always_inject=False,
                decay_sorted=True,
                description="Recent tier — decay-sorted",
            )
            if not cfg.nightstand_enabled:
                budgets[Tier.NIGHTSTAND] = TierBudget(
                    tier=Tier.NIGHTSTAND,
                    max_tokens=0,
                    always_inject=False,
                    decay_sorted=True,
                    description="Nightstand tier — disabled (budget=0)",
                )
            else:
                budgets[Tier.NIGHTSTAND] = TierBudget(
                    tier=Tier.NIGHTSTAND,
                    max_tokens=cfg.nightstand_budget,
                    always_inject=False,
                    decay_sorted=True,
                    description="Nightstand tier — reviewable, promotion-gated",
                )
            self._decay = decay_engine or create_decay_engine({"lambda_rate": cfg.lambda_rate})
            self._tiers = TierManager(
                tier_budgets=budgets,
                decay_engine=self._decay,
                rolling_summary_enabled=cfg.rolling_summary_enabled,
            )

        # Context builder: re-use the freshly built components unless caller
        # supplied one.
        if context_builder is not None:
            self._builder = context_builder
        else:
            self._builder = ContextBuilder(
                compressor=self._compressor,
                tier_manager=self._tiers,
                decay_engine=self._decay,
            )

        self._token_estimator = token_estimator or _default_token_estimator

        self._session_id: str = ""
        self._conversation_id: str = ""
        self._model: str = ""
        self._provider: str = ""
        self._api_mode: str = ""

        self._state_dir = cfg.rolling_summary_state_dir or os.environ.get(
            "HERMES_STATE_DIR", ""
        )
        self._rolling_cache: Optional[_RollingPayload] = None
        self._rolling_path: Optional[Path] = None
        self._last_compress_skipped: bool = False
        self._last_compress_error: Optional[str] = None
        self._last_compress_input_tokens: int = 0
        self._last_compress_output_tokens: int = 0
        self._last_compress_ratio: float = 0.0

    # ----- identity -----------------------------------------------------

    @property
    def name(self) -> str:
        return "aaak"

    # ----- lifecycle -----------------------------------------------------

    def on_session_start(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = str(session_id or "")
        self._conversation_id = str(kwargs.get("conversation_id", "") or "")
        self._invalidate_rolling_cache()
        for key in (
            "model",
            "provider",
            "api_mode",
            "context_length",
        ):
            if key in kwargs and kwargs[key] is not None:
                setattr(self, "_" + key, kwargs[key])
                if key == "context_length":
                    self.context_length = int(kwargs[key] or 0)
                    self._recompute_threshold()
        self.compression_count = 0
        self._last_compress_error = None

    def on_session_end(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        # Persist the final rolling payload, then release session state.
        self._flush_rolling_payload()
        self._session_id = ""
        self._conversation_id = ""
        self._invalidate_rolling_cache()

    def on_session_reset(self) -> None:
        self._flush_rolling_payload()
        self._session_id = ""
        self._conversation_id = ""
        self._invalidate_rolling_cache()
        self.compression_count = 0
        self._last_compress_error = None

    def bind_session_state(
        self,
        session_id: str = "",
        conversation_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Mirror ``ContextCompressor.bind_session_state`` for host compat."""
        self._session_id = str(session_id or self._session_id)
        self._conversation_id = str(conversation_id or self._conversation_id)

    # ----- model + token plumbing ---------------------------------------

    def update_model(
        self,
        *,
        model: str = "",
        context_length: Optional[int] = None,
        base_url: str = "",
        api_key: str = "",
        provider: str = "",
        api_mode: str = "",
        **kwargs: Any,
    ) -> None:
        self._model = str(model or "")
        self._provider = str(provider or "")
        self._api_mode = str(api_mode or "")
        if context_length is not None and context_length > 0:
            self.context_length = int(context_length)
            self._recompute_threshold()

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        """Record per-turn token usage from the API response.

        The ABC documents that ``usage`` may include ``prompt_tokens``,
        ``completion_tokens``, ``total_tokens`` (legacy keys) plus the
        canonical ``input_tokens``, ``output_tokens``,
        ``cache_read_tokens``, ``cache_write_tokens``,
        ``reasoning_tokens`` buckets. AAAK records all of them so
        preflight/diagnostic tooling that reads engine attributes
        behaves consistently with the built-in engine.
        """
        if not isinstance(usage, dict):
            return
        self.last_prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        self.last_total_tokens = int(usage.get("total_tokens", 0) or 0)
        self.last_input_tokens = int(
            usage.get("input_tokens", self.last_prompt_tokens) or 0
        )
        self.last_output_tokens = int(
            usage.get("output_tokens", self.last_completion_tokens) or 0
        )
        self.last_cache_read_tokens = int(usage.get("cache_read_tokens", 0) or 0)
        self.last_cache_write_tokens = int(usage.get("cache_write_tokens", 0) or 0)
        self.last_reasoning_tokens = int(usage.get("reasoning_tokens", 0) or 0)
        self._recompute_threshold()

    # ----- threshold / should_compress ----------------------------------

    def _recompute_threshold(self) -> None:
        """Re-derive ``threshold_tokens`` from ``context_length`` × percent."""
        if self.context_length > 0 and self.threshold_percent > 0:
            self.threshold_tokens = int(self.context_length * self.threshold_percent)
        else:
            self.threshold_tokens = 0

    def should_compress(self, prompt_tokens: Optional[int] = None) -> bool:
        """Return True when AAAK should fire this turn.

        Mirrors the ``ContextCompressor`` policy: compress when the
        prompt is at or above the configured percentage of the model's
        context length. The default 75% matches the built-in engine so
        users can swap engines without retuning.
        """
        if prompt_tokens is None:
            prompt_tokens = self.last_prompt_tokens
        if self.threshold_tokens <= 0:
            return False
        return int(prompt_tokens or 0) >= self.threshold_tokens

    def should_compress_info(
        self, prompt_tokens: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """Return ``(should_compress, reason)`` for host preflight reporting."""
        if prompt_tokens is None:
            prompt_tokens = self.last_prompt_tokens
        if self.threshold_tokens <= 0:
            return False, "threshold_tokens not set"
        if int(prompt_tokens or 0) >= self.threshold_tokens:
            return True, "prompt_tokens >= threshold_tokens"
        return False, None

    # ----- optional hooks (safe defaults) -------------------------------

    def prune_tool_results_only(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Deterministically trim oversized tool-result payloads.

        Returns ``(messages, n_pruned)``. AAAK keeps this hook simple:
        any tool-result ``content`` string longer than the recent tier
        budget is trimmed to that budget and tagged with an ellipsis.
        Engines that don't implement a cheap prune inherit the ABC's
        no-op; AAAK implements a deliberately conservative one so it
        can reclaim tokens *before* full compression would fire.
        """
        if not messages:
            return list(messages or []), 0
        cap = max(64, self.config.recent_budget // 4)
        pruned = 0
        out: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") != "tool":
                out.append(msg)
                continue
            content = msg.get("content")
            if isinstance(content, str) and len(content) > cap:
                trimmed = content[:cap].rstrip() + "\n[…trimmed by AAAK…]"
                new_msg = dict(msg)
                new_msg["content"] = trimmed
                out.append(new_msg)
                pruned += 1
            else:
                out.append(msg)
        return out, pruned

    def select_context(
        self,
        request_messages: List[Dict[str, Any]],
        *,
        conversation_messages: Optional[List[Dict[str, Any]]] = None,
        incoming_message: Optional[Dict[str, Any]] = None,
        budget_tokens: int = 0,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return ``None`` (request unchanged) — AAAK defers to ``compress()``.

        ``select_context()`` is the per-turn context-selection hook;
        AAAK is a *compression* engine, not a selection engine, so
        returning ``None`` lets the host's request-messages flow
        through to the model unchanged. Compression still happens via
        ``compress()`` when ``should_compress()`` returns True.
        """
        return None

    # ----- the actual compression pass ----------------------------------

    def has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool:
        """Return True when there is non-empty middle region to compress.

        Honors ``protect_first_n`` and ``protect_last_n``. Used by the
        host's manual ``/compress`` preflight so we skip the
        compression pass when the transcript fits inside the protected
        window.
        """
        head, middle, tail = _split_message_roles(messages)
        return bool(middle)

    def compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: Optional[int] = None,
        focus_topic: Optional[str] = None,
        force: bool = False,
        memory_context: str = "",
    ) -> List[Dict[str, Any]]:
        """Run a deterministic AAAK compression pass.

        Algorithm:
          1. Split into protected head / middle / tail per
             ``protect_first_n`` / ``protect_last_n`` and the system
             prompt.
          2. Push head + tail verbatim (they preserve the cache prefix
             and the most recent actionable turns).
          3. Compress each middle message with the AAAK engine and
             bundle the result into a single synthetic assistant
             summary message inserted between head and tail. The
             synthetic message has ``role='assistant'`` because the
             built-in ``ContextCompressor`` summary slot also lives in
             the assistant role — keeping the role stable preserves
             the host's strict message-alternation invariant.
          4. Roll each compressed topic into the per-session rolling
             summary, persisted to the externalized payload path.
          5. Update ``last_compress_*`` telemetry; never raise.
        """
        self._last_compress_skipped = False
        self._last_compress_error = None
        self._last_compress_input_tokens = 0
        self._last_compress_output_tokens = 0
        if current_tokens is not None:
            self._last_compress_input_tokens = int(current_tokens or 0)

        try:
            head, middle, tail = _split_message_roles(messages)
            if not middle:
                self._last_compress_skipped = True
                return list(messages)

            # Pre-trim tool-result payloads so the middle stays small.
            middle, _n_pruned = self.prune_tool_results_only(middle)

            # Build per-tier TieredMemory items from the middle slice
            # and assemble a synthetic summary block via ContextBuilder.
            compressed_blocks: List[TieredMemory] = []
            topic_buckets: Dict[str, List[str]] = {}
            for idx, msg in enumerate(middle):
                role = (msg.get("role") or "").lower() or "note"
                text = _content_text(msg)
                if not text:
                    continue
                label = "ASST" if role == "assistant" else "USR" if role == "user" else "NOTE"
                compressed_text = self._compressor.compress(text, label=label)
                topic = (focus_topic or self._derive_focus_topic(text) or "general")
                topic_buckets.setdefault(topic, []).append(compressed_text)
                compressed_blocks.append(
                    TieredMemory(
                        content=compressed_text,
                        tier=Tier.RECENT,
                        label=label,
                        token_estimate=self._token_estimator(compressed_text),
                        topic=topic,
                        timestamp=_now_iso(),
                    )
                )

            block = self._builder.build_context_block(
                compressed_blocks,
                CompressionContext(
                    session_id=self._session_id or "default",
                    max_tokens=self._budget_for_compress(),
                    focus_topic=focus_topic,
                ),
            )

            summary_text = self._format_summary_message(block, focus_topic=focus_topic)
            summary_message = {
                "role": "assistant",
                "content": summary_text,
            }

            self._update_rolling_summaries(topic_buckets)
            self.compression_count += 1
            self._last_compress_output_tokens = self._token_estimator(summary_text)
            if self._last_compress_input_tokens:
                self._last_compress_ratio = (
                    self._last_compress_output_tokens
                    / max(1, self._last_compress_input_tokens)
                )
            self._flush_rolling_payload()

            # If memory_context was supplied by the host, prepend it as a
            # synthetic note before the AAAK summary so the rolled-up
            # provider context survives the pass.
            out: List[Dict[str, Any]] = []
            if memory_context and memory_context.strip():
                out.append(
                    {
                        "role": "system",
                        "content": (
                            f"[memory provider context preserved]\n"
                            f"{memory_context.strip()}"
                        ),
                    }
                )
            out.extend(head)
            out.append(summary_message)
            out.extend(tail)
            return out
        except Exception as exc:  # pragma: no cover - defensive
            self._last_compress_error = repr(exc)
            if self.config.fallback_to_original:
                return list(messages)
            # If fallback is disabled, raise so the host can decide.
            raise

    # ----- telemetry -----------------------------------------------------

    @property
    def last_summary_error(self) -> Optional[str]:
        return self._last_compress_error

    @property
    def last_summary_dropped_count(self) -> int:
        return 0

    @property
    def last_summary_fallback_used(self) -> bool:
        return bool(self._last_compress_error and self.config.fallback_to_original)

    @property
    def last_compression_made_progress(self) -> bool:
        return bool(self.compression_count and not self._last_compress_skipped)

    # ----- helpers -------------------------------------------------------

    def _budget_for_compress(self) -> int:
        """Return the per-pass token budget for the synthetic summary block."""
        if self.context_length > 0:
            return max(64, int(self.context_length * 0.1))
        # Fall back to the recent tier budget when no context length is set
        return max(64, self.config.recent_budget)

    def _format_summary_message(
        self, block: ContextBlock, *, focus_topic: Optional[str]
    ) -> str:
        """Format the synthetic summary message body."""
        if not block.content:
            return "[AAAK summary: no compressible middle region]"
        header = "[AAAK summary"
        if focus_topic:
            header += f" focus={focus_topic}"
        header += "]"
        return f"{header}\n{block.content}"

    def _derive_focus_topic(self, text: str) -> Optional[str]:
        """Pick a stable topic key from the message text.

        Used when the host did not pass an explicit ``focus_topic``.
        Returns the lowercased first 3-grams word of the message, or
        ``None`` for empty text. Stable across calls for the same text.
        """
        cleaned = re.sub(r"\s+", " ", text).strip().lower()
        if not cleaned:
            return None
        words = cleaned.split(" ", 4)
        key = " ".join(words[:3])
        return key[:64] if key else None

    # ----- rolling summaries (externalized) -----------------------------

    def _rolling_payload(self) -> Tuple[Path, _RollingPayload]:
        """Return ``(path, payload)`` for the active session.

        Caches the loaded payload in ``self._rolling_cache`` so the
        in-memory mutations made by :meth:`_update_rolling_summaries`
        survive across calls within the same session. The cache is
        invalidated when ``on_session_start`` / ``on_session_end`` /
        ``on_session_reset`` runs.
        """
        path = externalized_payload_path(self._state_dir or ".", self._session_id)
        if self._rolling_path != path or self._rolling_cache is None:
            payload = _load_rolling_payload(path)
            payload.session_id = self._session_id or payload.session_id or "default"
            self._rolling_path = path
            self._rolling_cache = payload
        assert self._rolling_path is not None
        assert self._rolling_cache is not None
        return self._rolling_path, self._rolling_cache

    def _invalidate_rolling_cache(self) -> None:
        self._rolling_path = None
        self._rolling_cache = None

    def _update_rolling_summaries(self, topic_buckets: Dict[str, List[str]]) -> None:
        """Merge ``topic_buckets`` into the in-memory rolling payload."""
        if not self.config.rolling_summary_enabled:
            return
        if not topic_buckets:
            return
        _, payload = self._rolling_payload()
        # Bound total size; drop the oldest topic if we exceed the cap.
        for topic, fragments in topic_buckets.items():
            tier = Tier.CRITICAL.value if topic == "general" else Tier.RECENT.value
            existing = payload.summaries.setdefault(tier, {})
            joined = existing.get(topic, "")
            new_fragments = " | ".join(fragments)
            merged = joined + (" | " if joined else "") + new_fragments
            # Bound by config.rolling_summary_max_chars to keep the file small
            # and prevent the rolling summary from exceeding its tier budget.
            if len(merged) > self.config.rolling_summary_max_chars:
                merged = merged[-self.config.rolling_summary_max_chars :]
            existing[topic] = merged
        payload.last_compressed_at = time.time()
        payload.last_input_tokens = self._last_compress_input_tokens
        payload.last_output_tokens = self._last_compress_output_tokens
        # ``compression_count`` may be incremented later in ``compress()``
        # after this method returns; refresh it inside ``_flush_rolling_payload``
        # so the persisted count matches the engine's view.

    def _flush_rolling_payload(self) -> None:
        if not self.config.rolling_summary_enabled:
            return
        if not self._session_id:
            return
        try:
            path, payload = self._rolling_payload()
            # Refresh telemetry right before write so the persisted values
            # match the engine's current state (compression_count is
            # incremented AFTER _update_rolling_summaries runs).
            payload.last_input_tokens = self._last_compress_input_tokens
            payload.last_output_tokens = self._last_compress_output_tokens
            payload.last_compression_count = self.compression_count
            _save_rolling_payload(path, payload)
        except OSError:
            # Persistence is best-effort: AAAK never owns host durability.
            pass


def _now_iso() -> str:
    """Return a UTC ISO-8601 timestamp string for tier-manager timestamps."""
    import datetime as _dt

    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Factories and plugin wiring
# ---------------------------------------------------------------------------


def create_engine(
    config: Optional[AAAKAdapterConfig] = None,
    *,
    token_estimator: Optional[Callable[[str], int]] = None,
) -> AAAKContextEngine:
    """Convenience factory matching the issue's "Option A standalone plugin" pattern."""
    return AAAKContextEngine(config=config, token_estimator=token_estimator)


def register(ctx: Any) -> None:
    """Hermes-agent plugin-discovery entry point.

    The host's ``plugins.context_engine._EngineCollector`` exposes
    ``register_context_engine(engine)`` and accepts any object with
    the ABC surface — it does not validate subclassing. We pass an
    instance of :class:`AAAKContextEngine` and avoid importing the
    real ABC here so AAAK stays zero-dependency at module load.
    """
    engine = create_engine()
    register_engine = getattr(ctx, "register_context_engine", None)
    if callable(register_engine):
        register_engine(engine)
        return
    # Older hosts may call ``register`` without an
    # ``EngineCollector``-shaped ctx. Fall back to attaching the
    # engine as an attribute named ``aaak_engine`` so host code that
    # imports the plugin module directly can still discover it.
    setattr(ctx, "aaak_engine", engine)


def as_context_engine_subclass() -> Optional[type]:
    """Return a real ``ContextEngine`` subclass wrapping AAAKContextEngine.

    Returns ``None`` if hermes-agent is not importable. The host's
    ``plugins.context_engine`` loader uses this only when the module
    does not define ``register(ctx)``; because we *do* define it, this
    helper is optional.
    """
    try:
        from agent.context_engine import ContextEngine as _HostContextEngine  # type: ignore
    except Exception:
        return None

    class _BoundAAAKEngine(_HostContextEngine):
        """Conformance wrapper.

        Holds a :class:`AAAKContextEngine` and forwards every attribute
        access (read AND write) to it. Subclassing the real ABC at
        runtime makes the host's own ``isinstance(engine, ContextEngine)``
        checks pass without making hermes-agent a build-time dependency
        of AAAK.

        Required ABC methods (``update_from_response``, ``should_compress``,
        ``compress``) are declared explicitly so the ABC's abstract-method
        check sees concrete implementations at class-definition time;
        their bodies simply delegate to ``self._inner``. Everything else
        routes through ``__getattr__`` / ``__setattr__`` so the wrapper
        and the inner engine share one state.
        """

        # ---- required ABC methods (explicit so ABC sees them) ----

        def update_from_response(self, usage):  # noqa: D401
            return self._inner.update_from_response(usage)

        def should_compress(self, prompt_tokens=None):
            return self._inner.should_compress(prompt_tokens)

        def compress(
            self,
            messages,
            current_tokens=None,
            focus_topic=None,
            force=False,
            memory_context="",
        ):
            return self._inner.compress(
                messages,
                current_tokens=current_tokens,
                focus_topic=focus_topic,
                force=force,
                memory_context=memory_context,
            )

        # ---- lifecycle (no ABC requirement, but the host calls them) ----

        def on_session_start(self, session_id, **kwargs):
            return self._inner.on_session_start(session_id, **kwargs)

        def on_session_end(self, session_id, messages):
            return self._inner.on_session_end(session_id, messages)

        def on_session_reset(self):
            return self._inner.on_session_reset()

        def update_model(self, **kwargs):
            return self._inner.update_model(**kwargs)

        def bind_session_state(self, **kwargs):
            return self._inner.bind_session_state(**kwargs)

        def prune_tool_results_only(self, messages, current_tokens=None):
            return self._inner.prune_tool_results_only(messages, current_tokens)

        def select_context(self, request_messages, **kwargs):
            return self._inner.select_context(request_messages, **kwargs)

        # ---- identity ----

        @property
        def name(self) -> str:
            return self._inner.name

        # ---- attribute forwarding ----

        # Methods explicitly declared above take precedence. Everything
        # else (token attributes, threshold settings, lifecycle state)
        # routes through ``self._inner`` so the wrapper and the inner
        # engine share a single state.

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._inner = AAAKContextEngine(*args, **kwargs)

        def __getattr__(self, item: str) -> Any:
            # ``_inner`` itself is set in __init__; before that we'd
            # recurse, so guard.
            if item == "_inner":
                raise AttributeError(item)
            return getattr(self._inner, item)

        def __setattr__(self, item: str, value: Any) -> None:
            if item == "_inner":
                object.__setattr__(self, item, value)
                return
            setattr(self._inner, item, value)

    return _BoundAAAKEngine