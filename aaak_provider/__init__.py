"""
AAAK Compression Provider

Deterministic, AI-readable compression without requiring a decoder. The historical
~30x reduction is an unverified target. Adapted from Lumina MemPalace
(Bino5150/lumina).

This package is standalone and integration-oriented. It includes a
hermes-agent ``ContextEngine`` adapter (``aaak_provider.host_adapter``)
that is opt-in and zero-dependency at module load: the ABC is imported
lazily only when the host's plugin loader is invoked.
"""

from .compression import AAkCompressor, AAkConfig, DEFAULT_AAAK_ABBREV, create_compressor
from .tier_manager import TierManager, TierBudget, Tier, TieredMemory, DEFAULT_TIER_BUDGETS, create_tier_manager
from .temporal_decay import TemporalDecayEngine, create_decay_engine
from .context_builder import ContextBuilder, CompressionContext, ContextBlock, create_context_builder
from .host_adapter import (
    AAAKAdapterConfig,
    AAAKContextEngine,
    DEFAULT_ADAPTER_CONFIG,
    as_context_engine_subclass,
    create_engine,
    externalized_payload_path,
    register,
)

__all__ = [
    "AAkCompressor",
    "AAkConfig",
    "DEFAULT_AAAK_ABBREV",
    "create_compressor",
    "TierManager",
    "TierBudget",
    "Tier",
    "TieredMemory",
    "DEFAULT_TIER_BUDGETS",
    "create_tier_manager",
    "TemporalDecayEngine",
    "create_decay_engine",
    "ContextBuilder",
    "CompressionContext",
    "ContextBlock",
    "create_context_builder",
    "AAAKContextEngine",
    "AAAKAdapterConfig",
    "DEFAULT_ADAPTER_CONFIG",
    "create_engine",
    "register",
    "as_context_engine_subclass",
    "externalized_payload_path",
]

__version__ = "1.1.0"