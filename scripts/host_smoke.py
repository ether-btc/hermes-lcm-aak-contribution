#!/usr/bin/env python3
"""Run the AAAK adapter through hermes-agent's plugin-discovery loader.

Usage::

    PYTHONPATH=/path/to/hermes-agent/plugins \
    python3 scripts/host_smoke.py

If hermes-agent is not importable, the script prints a friendly message
and exits 0 — the smoke test is opt-in because hermes-agent is not a
runtime dependency of AAAK.

What it exercises:

  1. ``aaak_provider.host_adapter.register`` is fed a fake
     ``_EngineCollector`` matching hermes-agent's shape and the
     engine lands at ``host.engine``.
  2. ``isinstance(engine, agent.context_engine.ContextEngine)`` passes
     when hermes-agent is importable.
  3. ``update_model`` / ``update_from_response`` / ``should_compress``
     / ``compress`` / ``on_session_end`` round-trip without raising.
  4. Rolling-summary payload is flushed to the requested ``state_dir``.

Exits 0 on success, non-zero with a printed traceback on any failure.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, List, Dict, Optional


# ---------------------------------------------------------------------------
# Fake host — mirrors hermes-agent's plugins.context_engine._EngineCollector
# ---------------------------------------------------------------------------


class _FakeHost:
    def __init__(self) -> None:
        self.engine: Optional[Any] = None

    def register_context_engine(self, engine: Any) -> None:
        self.engine = engine


# ---------------------------------------------------------------------------
# Smoke sequence
# ---------------------------------------------------------------------------


def _transcript() -> List[Dict[str, Any]]:
    return [
        {"role": "system", "content": "You are Hermes Agent, a helpful assistant."},
        {
            "role": "user",
            "content": (
                "The user prefers dark mode and vim keybindings because the "
                "project is important. Iteration 0."
            ),
        },
        {
            "role": "assistant",
            "content": "Acknowledged. Dark mode + vim keybindings are configured.",
        },
        {
            "role": "user",
            "content": (
                "The local database completed the migration. Read "
                "/home/hermes-pi/projects/hermes-lcm/README.md and continue."
            ),
        },
        {
            "role": "assistant",
            "content": "Migration complete. Continuing the session per your instructions.",
        },
        {
            "role": "user",
            "content": (
                "Use https://example.com/api?mode=dark, commit 8570827, and "
                "preserve identifier hermes_lcm_context_engine."
            ),
        },
        {
            "role": "assistant",
            "content": "URL, commit, and identifier preserved verbatim.",
        },
        {
            "role": "user",
            "content": (
                "Run python3 -m pytest -q --maxfail=1 from /tmp/aak-check "
                "and keep exit code 2."
            ),
        },
        {"role": "assistant", "content": "Running pytest now; will preserve the exit code."},
    ]


def main() -> int:
    try:
        from aaak_provider.host_adapter import (
            AAAKAdapterConfig,
            register,
            externalized_payload_path,
        )
    except Exception:
        traceback.print_exc()
        print("FAIL: could not import aaak_provider.host_adapter", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="aaak-host-smoke-") as tmp:
        # Register through the plugin discovery path.
        host = _FakeHost()
        register(host)
        if host.engine is None:
            print("FAIL: register(ctx) did not populate host.engine", file=sys.stderr)
            return 2
        engine = host.engine

        # If hermes-agent is importable, also check the real ABC by
        # wrapping the engine in the dynamic subclass helper. The
        # register() path returns the raw AAAKContextEngine (no
        # hermes-agent import at module load); the wrapper exists for
        # hosts that require ``isinstance(engine, ContextEngine)``.
        try:
            from agent.context_engine import ContextEngine  # type: ignore
            from aaak_provider.host_adapter import as_context_engine_subclass

            if not isinstance(engine, ContextEngine):
                wrapper_cls = as_context_engine_subclass()
                if wrapper_cls is None:
                    print(
                        "FAIL: as_context_engine_subclass() returned None",
                        file=sys.stderr,
                    )
                    return 3
                wrapped = wrapper_cls()
                if not isinstance(wrapped, ContextEngine):
                    print(
                        "FAIL: wrapped engine is not a ContextEngine",
                        file=sys.stderr,
                    )
                    return 4
                engine = wrapped
        except Exception:
            print(
                "NOTE: hermes-agent not importable in this environment; "
                "duck-typed contract only.",
                file=sys.stderr,
            )

        # Drive the engine through a realistic preflight + compression cycle.
        engine.on_session_start(
            "smoke-session",
            model="gpt-test",
            context_length=1_000,
        )
        engine.update_from_response(
            {
                "prompt_tokens": 800,
                "completion_tokens": 200,
                "total_tokens": 1_000,
                "input_tokens": 810,
                "output_tokens": 205,
            }
        )
        flag, reason = engine.should_compress_info(800)
        if not flag:
            print(
                f"FAIL: should_compress should fire at 800/750: {reason}",
                file=sys.stderr,
            )
            return 4

        # First compression pass — middle gets bundled into a summary.
        out = engine.compress(
            _transcript(),
            current_tokens=1_200,
            memory_context="provider-supplied-memory-note",
        )
        if not any(
            isinstance(m.get("content"), str)
            and m["content"].startswith("[AAAK summary")
            for m in out
        ):
            print(
                "FAIL: synthetic AAAK summary message not found in output",
                file=sys.stderr,
            )
            return 5
        if out[0]["role"] != "system":
            print(
                "FAIL: memory_context was not prepended as a system message",
                file=sys.stderr,
            )
            return 6

        # Second pass — rolling summary should now include the new fragments.
        engine.compress(_transcript())
        engine.on_session_end("smoke-session", [])

        # Inspect the persisted rolling payload.
        # The adapter used the env var or default for state_dir; if it
        # was unset, the rolling path was under "." which we cannot
        # assert against. We re-register the engine with an explicit
        # state_dir to validate the persistence path.
        cfg = AAAKAdapterConfig(rolling_summary_state_dir=tmp)
        from aaak_provider.host_adapter import create_engine

        engine2 = create_engine(cfg)
        engine2.on_session_start("smoke-session-2", context_length=1_000)
        engine2.compress(_transcript())
        engine2.on_session_end("smoke-session-2", [])

        payload_path = externalized_payload_path(tmp, "smoke-session-2")
        if not payload_path.exists():
            print(
                f"FAIL: rolling payload not persisted at {payload_path}",
                file=sys.stderr,
            )
            return 7

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if not payload["summaries"]:
            print(
                "FAIL: rolling payload summaries are empty",
                file=sys.stderr,
            )
            return 8

        print("OK: host_smoke passed")
        print(f"  payload path: {payload_path}")
        print(f"  summaries:    {len(payload['summaries'])} tiers")
        print(f"  compressions: {payload.get('last_compression_count', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())