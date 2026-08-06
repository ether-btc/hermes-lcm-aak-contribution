"""
Tier Manager for AAAK 4-layer architecture.

Manages explicit token budgets per layer (L0-L3) with rolling summaries.
Adapted from Lumina MemPalace palace_closets/palace_rooms architecture.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Tier(Enum):
    """Memory tiers matching Lumina L0-L3 layers."""
    IDENTITY = "identity"      # L0: ~50 tokens - always injected, never changes
    CRITICAL = "critical"      # L1: ~120 tokens - always injected, updated on important changes
    RECENT = "recent"          # L2: ~300 tokens - injected at session start, decay-sorted
    NIGHTSTAND = "nightstand"  # NEW: ~200 tokens - auto-writes, reviewable, promotion-gated
    DEEP = "deep"              # L3: Unlimited - searched on demand, no injection


@dataclass
class TierBudget:
    """Token budget configuration per tier."""
    tier: Tier
    max_tokens: Optional[int]  # None = unlimited
    always_inject: bool = False
    decay_sorted: bool = False
    description: str = ""
    
    def __post_init__(self):
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive or None, got {self.max_tokens}")


# Default tier budgets matching Lumina
DEFAULT_TIER_BUDGETS: Dict[Tier, TierBudget] = {
    Tier.IDENTITY: TierBudget(
        tier=Tier.IDENTITY,
        max_tokens=50,
        always_inject=True,
        decay_sorted=False,
        description="Agent identity, user identity, platform, stack - never changes"
    ),
    Tier.CRITICAL: TierBudget(
        tier=Tier.CRITICAL,
        max_tokens=120,
        always_inject=True,
        decay_sorted=False,
        description="Critical facts, active preferences, current project - updated on important changes"
    ),
    Tier.RECENT: TierBudget(
        tier=Tier.RECENT,
        max_tokens=300,
        always_inject=False,
        decay_sorted=True,
        description="Recent sessions, active topics - decay-sorted, injected at session start"
    ),
    Tier.NIGHTSTAND: TierBudget(
        tier=Tier.NIGHTSTAND,
        max_tokens=200,
        always_inject=False,
        decay_sorted=True,
        description="Auto-generated content (idle sweeps) - reviewable, promotion-gated"
    ),
    Tier.DEEP: TierBudget(
        tier=Tier.DEEP,
        max_tokens=None,
        always_inject=False,
        decay_sorted=False,
        description="Full verbatim originals - searched on demand only"
    ),
}


@dataclass
class TieredMemory:
    """A memory item assigned to a specific tier."""
    content: str
    tier: Tier
    label: str
    token_estimate: int
    timestamp: str
    topic: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        if self.token_estimate <= 0:
            self.token_estimate = max(1, len(self.content) // 4)


class TierManager:
    """
    Manages the 4-layer (L0-L3) tiered memory architecture with explicit budgets.
    
    Features:
    - Explicit token budgets per tier (enforced)
    - Rolling summary per topic (Lumina closet pattern)
    - Temporal decay sorting for RECENT and NIGHTSTAND tiers
    - Context block builder respecting tier order and budgets
    """
    
    def __init__(
        self,
        tier_budgets: Optional[Dict[Tier, TierBudget]] = None,
        decay_engine: Optional["TemporalDecayEngine"] = None,
        rolling_summary_enabled: bool = True,
    ):
        self.tier_budgets = tier_budgets or DEFAULT_TIER_BUDGETS.copy()
        self.decay_engine = decay_engine
        self.rolling_summary_enabled = rolling_summary_enabled
        
        # Rolling summaries: topic -> {tier: compressed_content}
        self._rolling_summaries: Dict[str, Dict[Tier, str]] = {}
        
        # Track token usage per tier
        self._tier_token_usage: Dict[Tier, int] = {tier: 0 for tier in Tier}
    
    def assign_tier(self, content: str, label: str, topic: str = None) -> Tier:
        """
        Determine appropriate tier based on label/topic.
        
        Rules (from Lumina):
        - IDENTITY: "identity", "user", "platform", "stack"
        - CRITICAL: "preference", "critical", "active_project", "current"
        - RECENT: "session", "topic", "discovery" (default for recent items)
        - NIGHTSTAND: "auto-sweep", "dream", "idle" (auto-generated)
        - DEEP: "archive", "verbatim", "full" (large verbatim content)
        """
        label_lower = label.lower()
        topic_lower = (topic or "").lower()
        
        if any(k in label_lower or k in topic_lower for k in ["identity", "user", "platform", "stack"]):
            return Tier.IDENTITY
        if any(k in label_lower or k in topic_lower for k in ["preference", "critical", "active", "current"]):
            return Tier.CRITICAL
        if any(k in label_lower or k in topic_lower for k in ["auto", "dream", "idle", "sweep"]):
            return Tier.NIGHTSTAND
        if any(k in label_lower or k in topic_lower for k in ["archive", "verbatim", "full"]):
            return Tier.DEEP
        
        return Tier.RECENT
    
    def add_memory(self, memory: TieredMemory) -> bool:
        """
        Add a memory to its tier, enforcing budget.
        
        Returns True if added, False if budget exceeded (and not DEEP).
        """
        budget = self.tier_budgets.get(memory.tier)
        if budget is None:
            return False
        
        # DEEP tier has no budget limit
        if budget.max_tokens is None:
            return True
        
        # Check if adding would exceed budget
        new_usage = self._tier_token_usage[memory.tier] + memory.token_estimate
        if new_usage > budget.max_tokens:
            return False
        
        self._tier_token_usage[memory.tier] = new_usage
        return True
    
    def update_rolling_summary(
        self,
        topic: str,
        tier: Tier,
        new_content: str,
        label: str,
        compressor: "AAkCompressor"
    ) -> str:
        """
        Update rolling summary for a topic (Lumina closet pattern).
        
        Instead of creating new summary nodes, append to existing rolling summary.
        Returns the updated rolling summary.
        """
        if not self.rolling_summary_enabled:
            return compressor.compress(new_content, label)
        
        if topic not in self._rolling_summaries:
            self._rolling_summaries[topic] = {}
        
        existing = self._rolling_summaries[topic].get(tier, "")
        compressed = compressor.compress(new_content, None)  # No label for individual facts
        
        if existing:
            # Pipe-separated AAAK facts (from Lumina)
            merged = f"{existing} | {compressed}"
        else:
            merged = f"{label.upper()}: {compressed}"
        
        self._rolling_summaries[topic][tier] = merged
        return merged
    
    def get_rolling_summary(self, topic: str, tier: Tier) -> str:
        """Get rolling summary for a topic at a tier."""
        return self._rolling_summaries.get(topic, {}).get(tier, "")
    
    def get_all_rolling_summaries(self, tier: Tier) -> Dict[str, str]:
        """Get all rolling summaries for a tier."""
        return {
            topic: summaries[tier]
            for topic, summaries in self._rolling_summaries.items()
            if tier in summaries
        }
    
    def get_injection_order(self) -> List[Tier]:
        """
        Get tiers in injection order (identity -> critical -> recent -> nightstand).
        DEEP is never injected.
        """
        return [Tier.IDENTITY, Tier.CRITICAL, Tier.RECENT, Tier.NIGHTSTAND]
    
    def get_budget_status(self) -> Dict[Tier, Dict]:
        """Get current budget usage per tier."""
        return {
            tier: {
                "used": self._tier_token_usage[tier],
                "max": budget.max_tokens,
                "available": (budget.max_tokens - self._tier_token_usage[tier]) if budget.max_tokens else None,
                "percentage": (self._tier_token_usage[tier] / budget.max_tokens * 100) if budget.max_tokens else None,
            }
            for tier, budget in self.tier_budgets.items()
        }
    
    def reset_tier_usage(self, tier: Tier) -> None:
        """Reset token usage for a tier (e.g., at session start)."""
        self._tier_token_usage[tier] = 0
    
    def enforce_budget(
        self,
        tier: Tier,
        memories: List[TieredMemory],
        decay_engine: Optional["TemporalDecayEngine"] = None
    ) -> List[TieredMemory]:
        """
        Enforce budget by removing lowest-priority memories.
        
        For RECENT/NIGHTSTAND: sort by decay weight, keep highest.
        For IDENTITY/CRITICAL: should not exceed budget in normal operation.
        """
        budget = self.tier_budgets.get(tier)
        if budget is None or budget.max_tokens is None:
            return memories
        
        total_tokens = sum(m.token_estimate for m in memories)
        if total_tokens <= budget.max_tokens:
            return memories
        
        # Sort by priority
        if budget.decay_sorted and decay_engine:
            # Use decay engine to sort (highest weight = most recent/relevant)
            memories = decay_engine.sort_by_recency([
                {"content": m.content, "updated_at": m.timestamp, "token_estimate": m.token_estimate, "memory": m}
                for m in memories
            ])
            memories = [m["memory"] for m in memories]
        else:
            # For identity/critical: keep most recent (last added)
            memories = memories[-(budget.max_tokens // 50):]  # rough heuristic
        
        # Truncate to budget
        kept = []
        token_sum = 0
        for m in memories:
            if token_sum + m.token_estimate <= budget.max_tokens:
                kept.append(m)
                token_sum += m.token_estimate
            else:
                break
        
        return kept


def create_tier_manager(
    tier_budgets: Optional[Dict[Tier, TierBudget]] = None,
    decay_engine: Optional["TemporalDecayEngine"] = None,
    rolling_summary_enabled: bool = True,
) -> TierManager:
    """Factory function for creating tier manager with optional config."""
    return TierManager(
        tier_budgets=tier_budgets,
        decay_engine=decay_engine,
        rolling_summary_enabled=rolling_summary_enabled,
    )