"""
AAAK Compression Provider for hermes-lcm

Deterministic, AI-readable compression without requiring a decoder. The historical
~30x reduction is an unverified target. Adapted from Lumina MemPalace (Bino5150/lumina).

This package is standalone and integration-oriented. It does not currently
implement or register an active hermes-lcm runtime provider.
"""

from .compression import AAkCompressor, AAkConfig, DEFAULT_AAAK_ABBREV, create_compressor
from .tier_manager import TierManager, TierBudget, Tier, TieredMemory, DEFAULT_TIER_BUDGETS, create_tier_manager
from .temporal_decay import TemporalDecayEngine, create_decay_engine
from .context_builder import ContextBuilder, CompressionContext, ContextBlock, create_context_builder

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
]

__version__ = "1.0.0"