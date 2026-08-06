"""
Context Builder for AAAK integration with hermes-lcm.

Builds context blocks respecting tier order, budgets, and temporal decay.
Designed to integrate with hermes-lcm's existing context assembly pipeline.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from .compression import AAkCompressor, create_compressor
from .tier_manager import Tier, TierManager, TieredMemory, DEFAULT_TIER_BUDGETS, create_tier_manager
from .temporal_decay import TemporalDecayEngine, create_decay_engine


@dataclass
class CompressionContext:
    """Context for compression operation (matches hermes-lcm patterns)."""
    session_id: str
    max_tokens: int
    focus_topic: Optional[str] = None
    query: Optional[str] = None
    include_nightstand: bool = True
    tier_override: Optional[Dict[Tier, int]] = None  # Override budgets


@dataclass
class ContextBlock:
    """Built context block with metadata."""
    content: str
    total_tokens: int
    tier_breakdown: Dict[str, int]
    truncated: bool
    focus_topic: Optional[str] = None


class ContextBuilder:
    """
    Builds injection-ready context blocks from tiered memories.
    
    Integrates with hermes-lcm's context assembly:
    - Respects tier injection order (identity -> critical -> recent -> nightstand)
    - Enforces explicit token budgets per tier
    - Applies temporal decay sorting for recent/nightstand
    - Supports focus topic filtering
    - Returns truncated indicator for downstream handling
    """
    
    def __init__(
        self,
        compressor: Optional[AAkCompressor] = None,
        tier_manager: Optional[TierManager] = None,
        decay_engine: Optional[TemporalDecayEngine] = None,
    ):
        self.compressor = compressor or create_compressor()
        self.tier_manager = tier_manager or create_tier_manager()
        self.decay_engine = decay_engine or create_decay_engine()
        
        # Ensure tier manager has decay engine
        if self.tier_manager.decay_engine is None:
            self.tier_manager.decay_engine = self.decay_engine
    
    def build_context_block(
        self,
        memories: List[TieredMemory],
        context: CompressionContext
    ) -> ContextBlock:
        """
        Build context block from memories.
        
        Args:
            memories: List of tiered memories
            context: Compression context with max_tokens, focus_topic, etc.
            
        Returns:
            ContextBlock with assembled content and metadata
        """
        # Group memories by tier
        tiered_memories = {tier: [] for tier in Tier}
        for mem in memories:
            tiered_memories[mem.tier].append(mem)
        
        # Apply focus topic filter if specified
        if context.focus_topic:
            for tier in tiered_memories:
                tiered_memories[tier] = [
                    m for m in tiered_memories[tier]
                    if context.focus_topic.lower() in (m.topic or "").lower()
                ]
        
        # Sort RECENT and NIGHTSTAND by temporal decay
        for tier in [Tier.RECENT, Tier.NIGHTSTAND]:
            if tiered_memories[tier] and self.tier_manager.tier_budgets[tier].decay_sorted:
                # Convert to dict format for decay engine
                mem_dicts = [
                    {"content": m.content, "updated_at": m.timestamp, "memory": m}
                    for m in tiered_memories[tier]
                ]
                sorted_dicts = self.decay_engine.sort_by_recency(mem_dicts)
                tiered_memories[tier] = [d["memory"] for d in sorted_dicts]
        
        # Build content respecting tier order and budgets
        injection_order = self.tier_manager.get_injection_order()
        if not context.include_nightstand:
            injection_order = [t for t in injection_order if t != Tier.NIGHTSTAND]
        
        parts = []
        tier_breakdown = {}
        total_tokens = 0
        truncated = False
        
        for tier in injection_order:
            budget = self.tier_manager.tier_budgets.get(tier)
            if budget is None:
                continue
            
            # Determine effective budget for this tier
            tier_max = budget.max_tokens
            if context.tier_override and tier in context.tier_override:
                tier_max = context.tier_override[tier]
            
            # If tier has no budget limit, use remaining context budget
            if tier_max is None:
                remaining = context.max_tokens - total_tokens
                if remaining <= 0:
                    truncated = True
                    break
                tier_max = remaining
            
            # Get memories for this tier
            mem_list = tiered_memories[tier]
            if not mem_list:
                tier_breakdown[tier.value] = 0
                continue
            
            # Enforce budget
            mem_list = self.tier_manager.enforce_budget(tier, mem_list, self.decay_engine)
            
            # Build tier content
            tier_parts = []
            tier_tokens = 0
            
            for mem in mem_list:
                # Compress if not already compressed
                if mem.label and not mem.content.startswith(mem.label.upper() + ":"):
                    compressed = self.compressor.compress(mem.content, mem.label)
                else:
                    compressed = mem.content
                
                # Use local token estimate to avoid mutating input memory
                token_estimate = self.compressor.estimate_tokens(compressed)
                
                if tier_tokens + token_estimate <= tier_max:
                    tier_parts.append(compressed)
                    tier_tokens += token_estimate
                else:
                    truncated = True
                    break
            
            if tier_parts:
                # Join with newlines for readability
                tier_content = "\n".join(tier_parts)
                parts.append(tier_content)
                total_tokens += tier_tokens
                tier_breakdown[tier.value] = tier_tokens
            
            # Check if we've hit overall budget
            if total_tokens >= context.max_tokens:
                truncated = True
                break
        
        # Join all tiers with clear separation
        content = "\n\n".join(parts) if parts else ""
        
        return ContextBlock(
            content=content,
            total_tokens=total_tokens,
            tier_breakdown=tier_breakdown,
            truncated=truncated,
            focus_topic=context.focus_topic
        )
    
    def build_from_rolling_summaries(
        self,
        tier_manager: TierManager,
        context: CompressionContext
    ) -> ContextBlock:
        """
        Build context block directly from rolling summaries (Lumina closet pattern).
        
        This is the preferred path when rolling summaries are available.
        """
        injection_order = self.tier_manager.get_injection_order()
        if not context.include_nightstand:
            injection_order = [t for t in injection_order if t != Tier.NIGHTSTAND]
        
        parts = []
        tier_breakdown = {}
        total_tokens = 0
        truncated = False
        
        for tier in injection_order:
            budget = self.tier_manager.tier_budgets.get(tier)
            if budget is None:
                continue
            
            tier_max = budget.max_tokens
            if context.tier_override and tier in context.tier_override:
                tier_max = context.tier_override[tier]
            
            if tier_max is None:
                remaining = context.max_tokens - total_tokens
                if remaining <= 0:
                    truncated = True
                    break
                tier_max = remaining
            
            # Get all rolling summaries for this tier
            summaries = tier_manager.get_all_rolling_summaries(tier)
            
            # Apply focus topic filter
            if context.focus_topic:
                summaries = {
                    topic: content for topic, content in summaries.items()
                    if context.focus_topic.lower() in topic.lower()
                }
            
            # Sort by temporal decay if enabled
            if budget.decay_sorted:
                # Convert to dict for decay engine (use topic as key, assume recent)
                # Note: rolling summaries don't have individual timestamps
                # This is a limitation - in practice, track last_update per topic
                pass
            
            # Build tier content
            tier_parts = []
            tier_tokens = 0
            
            for topic, content in summaries.items():
                tokens = self.compressor.estimate_tokens(content)
                if tier_tokens + tokens <= tier_max:
                    tier_parts.append(content)
                    tier_tokens += tokens
                else:
                    truncated = True
                    break
            
            if tier_parts:
                tier_content = "\n".join(tier_parts)
                parts.append(tier_content)
                total_tokens += tier_tokens
                tier_breakdown[tier.value] = tier_tokens
            
            if total_tokens >= context.max_tokens:
                truncated = True
                break
        
        content = "\n\n".join(parts) if parts else ""
        
        return ContextBlock(
            content=content,
            total_tokens=total_tokens,
            tier_breakdown=tier_breakdown,
            truncated=truncated,
            focus_topic=context.focus_topic
        )


def create_context_builder(config: Optional[Dict] = None) -> ContextBuilder:
    """Factory function for creating context builder with optional config."""
    compressor = create_compressor(config.get("compressor") if config else None)
    decay_engine = create_decay_engine(config.get("decay_engine") if config else None)
    tier_manager = create_tier_manager(
        tier_budgets=config.get("tier_budgets") if config else None,
        decay_engine=decay_engine,
        rolling_summary_enabled=config.get("rolling_summary_enabled", True) if config else True,
    )
    return ContextBuilder(compressor=compressor, tier_manager=tier_manager, decay_engine=decay_engine)