"""
Temporal Decay Engine for AAAK compression.

Exponential forgetting curve: w(t) = e^(-λ × t)
Where λ = 0.05/day → ~22% retention after 30 days.

Adapted from Lumina MemPalace (tools/temporal_decay.py)
"""

import math
from datetime import datetime
from typing import List, Dict, Any, Optional


class TemporalDecayEngine:
    """
    Exponential decay weighting for memory recency.
    
    Formula: w(t) = e^(-λ × t)
    - λ (lambda_rate): decay rate per day (default 0.05)
    - t: time elapsed in days
    - Result: weight between 0.01 and 1.0
    
    At λ=0.05/day:
    - 1 day: 95% retention
    - 7 days: 70% retention
    - 30 days: 78% retention (wait, let me recalculate)
    Actually: e^(-0.05 * 30) = e^(-1.5) ≈ 0.223 = 22.3% retention at 30 days
    """
    
    def __init__(self, lambda_rate: float = 0.05):
        """
        Initialize decay engine.
        
        Args:
            lambda_rate: Decay rate per day (default 0.05)
        """
        if not math.isfinite(lambda_rate) or lambda_rate <= 0:
            raise ValueError("lambda_rate must be a finite positive number")
        self.lambda_rate = lambda_rate
        # Time constant τ = 1/λ (in days), convert to seconds for timestamp math
        self.tau_days = 1.0 / lambda_rate
        self.tau_seconds = self.tau_days * 86400
    
    def decay_weight(self, timestamp: str) -> float:
        """
        Calculate decay weight for a timestamp.
        
        Args:
            timestamp: ISO format timestamp string
            
        Returns:
            Weight between 0.01 and 1.0
        """
        if not timestamp:
            return 1.0
        
        try:
            # Parse timestamp
            if 'T' in timestamp:
                mem_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                mem_time = datetime.fromisoformat(timestamp)
            
            # Calculate time delta in days
            delta_seconds = datetime.now().timestamp() - mem_time.timestamp()
            delta_days = delta_seconds / 86400
            
            # Exponential decay: w = e^(-λ * t)
            weight = math.exp(-self.lambda_rate * delta_days)
            
            # Clamp to reasonable range
            return max(0.01, min(1.0, weight))
            
        except Exception:
            # On parse error, return neutral weight
            return 0.5
    
    def sort_by_recency(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort memories by decay weight (highest = most recent/relevant).
        
        Args:
            memories: List of dicts with 'updated_at' or 'timestamp' key
            
        Returns:
            Sorted list (highest weight first)
        """
        def get_weight(m: Dict[str, Any]) -> float:
            ts = m.get("updated_at") or m.get("timestamp") or ""
            return self.decay_weight(ts)
        
        return sorted(memories, key=get_weight, reverse=True)
    
    def filter_by_weight(
        self,
        memories: List[Dict[str, Any]],
        min_weight: float = 0.1
    ) -> List[Dict[str, Any]]:
        """Filter memories below minimum weight threshold."""
        return [m for m in memories if self.decay_weight(m.get("updated_at") or m.get("timestamp") or "") >= min_weight]
    
    def get_weight_at_days(self, days: float) -> float:
        """Get theoretical weight at N days (for testing/analysis)."""
        weight = math.exp(-self.lambda_rate * days)
        return max(0.01, min(1.0, weight))


def create_decay_engine(config: Optional[Dict] = None) -> TemporalDecayEngine:
    """Factory function for creating decay engine with optional config."""
    if config is None:
        return TemporalDecayEngine()
    
    lambda_rate = config.get("lambda_rate", 0.05)
    return TemporalDecayEngine(lambda_rate=lambda_rate)