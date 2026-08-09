"""Tests for AAAK Compression Provider.

Tests cover compression engine, tier management, temporal decay, and context building.
"""

import pytest
from datetime import datetime
import time
from aaak_provider.compression import (
    AAkCompressor,
    AAkConfig,
    DEFAULT_AAAK_ABBREV,
    create_compressor,
)
from aaak_provider.tier_manager import (
    Tier,
    TierBudget,
    TieredMemory,
    TierManager,
    DEFAULT_TIER_BUDGETS,
    create_tier_manager,
)
from aaak_provider.temporal_decay import (
    TemporalDecayEngine,
    create_decay_engine,
)
from aaak_provider.context_builder import (
    ContextBuilder,
    CompressionContext,
    ContextBlock,
    create_context_builder,
)


# ============================================================================
# Compression Engine Tests
# ============================================================================

class TestAAkCompressor:
    """Tests for the AAAK compression engine."""
    
    def test_basic_compression(self):
        """Test basic compression with known abbreviations."""
        compressor = AAkCompressor()
        text = "The user prefers dark mode and vim keybindings"
        result = compressor.compress(text, "PREF")
        
        assert "PREF:" in result
        assert "dark-mode" in result
        assert "vim-bindings" in result
        # Fillers should be stripped
        assert "the " not in result.lower()
        assert "and" in result or "+" in result  # 'and' -> '+'
    
    def test_no_label(self):
        """Test compression without label."""
        compressor = AAkCompressor()
        text = "Project Lumina is in progress"
        result = compressor.compress(text)
        
        assert "PROJ:" not in result  # No label prepended
        assert "LUM" in result or "Lumina" in result
        assert "WIP" in result or "in progress" in result
    
    def test_short_text_no_compression(self):
        """Test that very short text is not compressed (below threshold)."""
        compressor = AAkCompressor(AAkConfig(min_line_length=20))
        text = "Hi"
        result = compressor.compress(text, "TEST")
        
        # Should return as-is with label
        assert result == "TEST: Hi"
    
    def test_filler_word_stripping(self):
        """Test that filler words are stripped."""
        compressor = AAkCompressor()
        text = "The user is very really just working on the project"
        result = compressor.compress(text, "SESS")
        
        # Fillers should be gone
        assert "the " not in result.lower()
        assert "is " not in result.lower()
        assert "very " not in result.lower()
        assert "really " not in result.lower()
        assert "just " not in result.lower()
    
    def test_abbreviation_map_extension(self):
        """Test adding custom abbreviations."""
        compressor = AAkCompressor()
        compressor.add_abbreviation("hermes", "HER")
        
        text = "Hermes agent is running"
        result = compressor.compress(text)
        
        assert "HER" in result
    
    def test_compress_lines(self):
        """Test batch compression of multiple lines."""
        compressor = AAkCompressor()
        lines = [
            "User prefers dark mode",
            "Project Lumina in progress",
            "Session started now"
        ]
        labels = ["PREF", "PROJ", "SESS"]
        results = compressor.compress_lines(lines, labels)
        
        assert len(results) == 3
        assert all(":" in r for r in results)
        assert "PREF:" in results[0]
        assert "PROJ:" in results[1]
        assert "SESS:" in results[2]
    
    def test_token_estimation(self):
        """Test token estimation heuristic."""
        compressor = AAkCompressor()
        
        # ~4 chars per token
        assert compressor.estimate_tokens("hello") == 1  # 5 chars -> 1
        assert compressor.estimate_tokens("hello world") == 2  # 11 chars -> 2
        assert compressor.estimate_tokens("") == 1  # minimum 1
    
    def test_case_insensitive_abbreviation(self):
        """Test that abbreviations work case-insensitively."""
        compressor = AAkCompressor()
        
        text1 = "Project Lumina is running"
        text2 = "project lumina is running"
        text3 = "PROJECT LUMINA IS RUNNING"
        
        r1 = compressor.compress(text1)
        r2 = compressor.compress(text2)
        r3 = compressor.compress(text3)
        
        assert "PROJ" in r1
        assert "PROJ" in r2
        assert "PROJ" in r3
        assert "LUM" in r1
        assert "LUM" in r2
        assert "LUM" in r3

    def test_abbreviations_do_not_rewrite_substrings(self):
        compressor = AAkCompressor()
        result = compressor.compress("Candy and database")
        assert "Candy" in result
        assert "+" in result
        assert "DB" in result

    def test_custom_filler_words_are_used(self):
        compressor = AAkCompressor(AAkConfig(filler_words={"customfiller", "the"}))
        result = compressor.compress("Keep customfiller but preserve the")
        assert "customfiller" not in result
        assert "the" not in result.lower()

    @pytest.mark.parametrize(
        "config",
        [
            AAkConfig(abbreviation_map={}),
            AAkConfig(abbreviation_map={"project": ""}),
            AAkConfig(abbreviation_map={"project": 1}),
            AAkConfig(abbreviation_map={1: "PROJ"}),
            AAkConfig(abbreviation_map={"Project": "PROJ", "project": "P"}),
            AAkConfig(min_line_length=-1),
            AAkConfig(min_line_length=True),
        ],
    )
    def test_invalid_configuration_is_rejected(self, config):
        with pytest.raises((TypeError, ValueError)):
            AAkCompressor(config)

    def test_factory_custom_filler_words_extend_defaults(self):
        compressor = create_compressor({"filler_words": ["customfiller"]})
        result = compressor.compress("The customfiller user is running")
        assert "customfiller" not in result.lower()
        assert "the " not in result.lower()
        assert "is " not in result.lower()

    @pytest.mark.parametrize("config", [[], "not-a-map", {"unknown": 1}])
    def test_factory_rejects_malformed_config(self, config):
        with pytest.raises((TypeError, ValueError)):
            create_compressor(config)

    def test_load_abbreviation_map_replaces_with_validated_map(self, tmp_path):
        path = tmp_path / "abbreviations.json"
        path.write_text('{"hermes": "HER"}', encoding="utf-8")

        compressor = AAkCompressor()
        compressor.load_abbreviation_map(str(path))

        assert compressor.compress("Hermes agent is running") == "HER agent running"

    @pytest.mark.parametrize("payload", ["[]", '{"project": ""}', '{"Project": "P", "project": "Q"}'])
    def test_load_abbreviation_map_rejects_invalid_json_map(self, tmp_path, payload):
        path = tmp_path / "abbreviations.json"
        path.write_text(payload, encoding="utf-8")

        with pytest.raises((TypeError, ValueError)):
            AAkCompressor().load_abbreviation_map(str(path))


# ============================================================================
# Tier Manager Tests
# ============================================================================

class TestTierManager:
    """Tests for the tier management system."""
    
    def test_tier_budgets_exist(self):
        """Test that all default tier budgets are defined."""
        assert Tier.IDENTITY in DEFAULT_TIER_BUDGETS
        assert Tier.CRITICAL in DEFAULT_TIER_BUDGETS
        assert Tier.RECENT in DEFAULT_TIER_BUDGETS
        assert Tier.NIGHTSTAND in DEFAULT_TIER_BUDGETS
        assert Tier.DEEP in DEFAULT_TIER_BUDGETS
        
        # Check budget values match Lumina
        assert DEFAULT_TIER_BUDGETS[Tier.IDENTITY].max_tokens == 50
        assert DEFAULT_TIER_BUDGETS[Tier.CRITICAL].max_tokens == 120
        assert DEFAULT_TIER_BUDGETS[Tier.RECENT].max_tokens == 300
        assert DEFAULT_TIER_BUDGETS[Tier.NIGHTSTAND].max_tokens == 200
        assert DEFAULT_TIER_BUDGETS[Tier.DEEP].max_tokens is None
    
    def test_tier_assignment(self):
        """Test automatic tier assignment based on label/topic."""
        manager = TierManager()
        
        assert manager.assign_tier("content", "identity") == Tier.IDENTITY
        assert manager.assign_tier("content", "user") == Tier.IDENTITY
        assert manager.assign_tier("content", "preference") == Tier.CRITICAL
        assert manager.assign_tier("content", "active_project") == Tier.CRITICAL
        assert manager.assign_tier("content", "session") == Tier.RECENT
        assert manager.assign_tier("content", "discovery") == Tier.RECENT
        assert manager.assign_tier("content", "auto_sweep") == Tier.NIGHTSTAND
        assert manager.assign_tier("content", "dream") == Tier.NIGHTSTAND
        assert manager.assign_tier("content", "archive") == Tier.DEEP
        assert manager.assign_tier("content", "verbatim") == Tier.DEEP
    
    def test_add_memory_enforces_budget(self):
        """Test that budget is enforced when adding memories."""
        manager = TierManager()
        
        # Create memories that would exceed IDENTITY budget (50 tokens)
        mem1 = TieredMemory(
            content="User identity info",
            tier=Tier.IDENTITY,
            label="IDENTITY",
            token_estimate=30,
            timestamp="2026-01-01T00:00:00"
        )
        mem2 = TieredMemory(
            content="More identity info",
            tier=Tier.IDENTITY,
            label="IDENTITY",
            token_estimate=30,
            timestamp="2026-01-01T00:00:00"
        )
        
        assert manager.add_memory(mem1) is True
        assert manager.add_memory(mem2) is False  # Would exceed 50 token budget
    
    def test_deep_tier_unlimited(self):
        """Test that DEEP tier has no budget limit."""
        manager = TierManager()
        
        # Add many large memories to DEEP
        for i in range(100):
            mem = TieredMemory(
                content=f"Large content {i} " * 100,
                tier=Tier.DEEP,
                label="ARCHIVE",
                token_estimate=1000,
                timestamp="2026-01-01T00:00:00"
            )
            assert manager.add_memory(mem) is True
    
    def test_rolling_summary_update(self):
        """Test rolling summary update (Lumina closet pattern)."""
        from aaak_provider.compression import AAkCompressor
        compressor = AAkCompressor()
        manager = TierManager(rolling_summary_enabled=True)
        
        # First addition creates new summary
        summary1 = manager.update_rolling_summary(
            topic="preferences",
            tier=Tier.CRITICAL,
            new_content="User prefers dark mode",
            label="PREF",
            compressor=compressor
        )
        
        assert "PREF:" in summary1
        assert "dark-mode" in summary1
        
        # Second addition appends with pipe
        summary2 = manager.update_rolling_summary(
            topic="preferences",
            tier=Tier.CRITICAL,
            new_content="User prefers vim keybindings",
            label="PREF",
            compressor=compressor
        )
        
        assert "|" in summary2
        assert "dark-mode" in summary2
        assert "vim-bindings" in summary2
    
    def test_rolling_summary_disabled(self):
        """Test that rolling summary can be disabled."""
        from aaak_provider.compression import AAkCompressor
        compressor = AAkCompressor()
        manager = TierManager(rolling_summary_enabled=False)
        
        summary1 = manager.update_rolling_summary(
            topic="test",
            tier=Tier.RECENT,
            new_content="First fact",
            label="SESS",
            compressor=compressor
        )
        
        summary2 = manager.update_rolling_summary(
            topic="test",
            tier=Tier.RECENT,
            new_content="Second fact",
            label="SESS",
            compressor=compressor
        )
        
        # Should not accumulate, just return compressed new content each time
        assert "SESS:" in summary1
        assert "SESS:" in summary2
        assert "First" in summary1
        assert "Second" in summary2
    
    def test_budget_status(self):
        """Test budget status reporting."""
        manager = TierManager()
        
        mem = TieredMemory(
            content="Test",
            tier=Tier.IDENTITY,
            label="IDENTITY",
            token_estimate=25,
            timestamp="2026-01-01T00:00:00"
        )
        manager.add_memory(mem)
        
        status = manager.get_budget_status()
        
        assert status[Tier.IDENTITY]["used"] == 25
        assert status[Tier.IDENTITY]["max"] == 50
        assert status[Tier.IDENTITY]["available"] == 25
        assert status[Tier.IDENTITY]["percentage"] == 50.0
        assert status[Tier.DEEP]["max"] is None


# ============================================================================
# Temporal Decay Tests
# ============================================================================

class TestTemporalDecayEngine:
    """Tests for temporal decay engine."""
    
    def test_decay_weight_recent(self):
        """Test that recent timestamps get high weight."""
        engine = TemporalDecayEngine(lambda_rate=0.05)
        
        # Current time
        now = datetime.now().isoformat()
        weight = engine.decay_weight(now)
        assert weight > 0.9

    @pytest.mark.parametrize("rate", [0, -1, float("nan"), float("inf")])
    def test_invalid_decay_rate_rejected(self, rate):
        with pytest.raises(ValueError):
            TemporalDecayEngine(lambda_rate=rate)
    
    def test_decay_weight_old(self):
        """Test that old timestamps get low weight."""
        engine = TemporalDecayEngine(lambda_rate=0.05)
        
        # 30 days ago
        old_ts = datetime.fromtimestamp(time.time() - 30 * 86400).isoformat()
        weight = engine.decay_weight(old_ts)
        
        # e^(-0.05 * 30) = e^(-1.5) ≈ 0.223
        assert 0.2 < weight < 0.25
    
    def test_decay_weight_invalid_timestamp(self):
        """Test handling of invalid timestamps."""
        engine = TemporalDecayEngine()
        
        assert engine.decay_weight("") == 1.0
        assert engine.decay_weight("invalid") == 0.5
        assert engine.decay_weight(None) == 1.0  # type: ignore
    
    def test_sort_by_recency(self):
        """Test sorting memories by recency."""
        engine = TemporalDecayEngine(lambda_rate=0.05)
        
        now = time.time()
        memories = [
            {"content": "old", "updated_at": datetime.fromtimestamp(now - 10 * 86400).isoformat()},
            {"content": "new", "updated_at": datetime.fromtimestamp(now - 1 * 86400).isoformat()},
            {"content": "medium", "updated_at": datetime.fromtimestamp(now - 5 * 86400).isoformat()},
        ]
        
        sorted_mem = engine.sort_by_recency(memories)
        
        assert sorted_mem[0]["content"] == "new"
        assert sorted_mem[1]["content"] == "medium"
        assert sorted_mem[2]["content"] == "old"
    
    def test_get_weight_at_days(self):
        """Test theoretical weight calculation."""
        engine = TemporalDecayEngine(lambda_rate=0.05)
        
        w0 = engine.get_weight_at_days(0)
        w1 = engine.get_weight_at_days(1)
        w7 = engine.get_weight_at_days(7)
        w30 = engine.get_weight_at_days(30)
        
        assert w0 == 1.0
        assert 0.9 < w1 < 1.0
        assert 0.65 < w7 < 0.75
        assert 0.2 < w30 < 0.25


# ============================================================================
# Context Builder Tests
# ============================================================================

class TestContextBuilder:
    """Tests for context block building."""
    
    def test_build_context_block_basic(self):
        """Test basic context block building."""
        builder = create_context_builder()
        
        memories = [
            TieredMemory(
                content="User name is Alice",
                tier=Tier.IDENTITY,
                label="IDENTITY",
                token_estimate=10,
                timestamp="2026-01-01T00:00:00"
            ),
            TieredMemory(
                content="Prefers dark mode",
                tier=Tier.CRITICAL,
                label="PREF",
                token_estimate=8,
                timestamp="2026-01-01T00:00:00"
            ),
            TieredMemory(
                content="Working on Lumina project",
                tier=Tier.RECENT,
                label="PROJ",
                token_estimate=15,
                timestamp="2026-01-01T00:00:00"
            ),
        ]
        
        context = CompressionContext(
            session_id="test",
            max_tokens=500,
            include_nightstand=True
        )
        
        block = builder.build_context_block(memories, context)
        
        assert block.total_tokens > 0
        assert "identity" in block.tier_breakdown
        assert "critical" in block.tier_breakdown
        assert "recent" in block.tier_breakdown
        assert not block.truncated
    
    def test_context_block_truncation(self):
        """Test that context block truncates at max_tokens."""
        builder = create_context_builder()
        
        # Create many memories that exceed budget
        memories = []
        for i in range(20):
            memories.append(TieredMemory(
                content=f"Memory item number {i} with substantial content that will not compress down to tiny size " * 3,
                tier=Tier.RECENT,
                label="SESS",
                token_estimate=80,
                timestamp="2026-01-01T00:00:00"
            ))
        
        # Override RECENT tier budget to be very small
        context = CompressionContext(
            session_id="test",
            max_tokens=500,
            tier_override={Tier.RECENT: 100},
            include_nightstand=False
        )
        
        block = builder.build_context_block(memories, context)
        
        assert block.truncated
        assert block.tier_breakdown.get("recent", 0) <= 100
    
    def test_focus_topic_filter(self):
        """Test focus topic filtering."""
        builder = create_context_builder()
        
        memories = [
            TieredMemory(
                content="User likes dark mode",
                tier=Tier.CRITICAL,
                label="PREF",
                token_estimate=10,
                timestamp="2026-01-01T00:00:00",
                topic="preferences"
            ),
            TieredMemory(
                content="Project Lumina active",
                tier=Tier.CRITICAL,
                label="PROJ",
                token_estimate=10,
                timestamp="2026-01-01T00:00:00",
                topic="projects"
            ),
        ]
        
        context = CompressionContext(
            session_id="test",
            max_tokens=500,
            focus_topic="preferences",
            include_nightstand=False
        )
        
        block = builder.build_context_block(memories, context)
        
        # Note: compression changes "dark mode" -> "dark-mode"
        assert "dark-mode" in block.content.lower()
        assert "lumina" not in block.content.lower()
    
    def test_tier_override(self):
        """Test tier budget override."""
        builder = create_context_builder()
        
        memories = [
            TieredMemory(
                content="Recent item " * 20,
                tier=Tier.RECENT,
                label="SESS",
                token_estimate=100,
                timestamp="2026-01-01T00:00:00"
            ),
        ]
        
        # Override RECENT budget to be smaller
        context = CompressionContext(
            session_id="test",
            max_tokens=500,
            tier_override={Tier.RECENT: 50},
            include_nightstand=False
        )
        
        block = builder.build_context_block(memories, context)
        
        assert block.tier_breakdown.get("recent", 0) <= 50
    
    def test_nightstand_exclusion(self):
        """Test nightstand tier exclusion."""
        builder = create_context_builder()
        
        memories = [
            TieredMemory(
                content="Auto-generated sweep content",
                tier=Tier.NIGHTSTAND,
                label="AUTO",
                token_estimate=50,
                timestamp="2026-01-01T00:00:00"
            ),
        ]
        
        context = CompressionContext(
            session_id="test",
            max_tokens=500,
            include_nightstand=False
        )
        
        block = builder.build_context_block(memories, context)
        
        assert block.total_tokens == 0
        assert "nightstand" not in block.tier_breakdown


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for full AAAK pipeline."""
    
    def test_full_pipeline(self):
        """Test complete pipeline: compress -> tier -> decay -> context."""
        from aaak_provider.compression import AAkCompressor
        from aaak_provider.tier_manager import TierManager, TieredMemory, Tier
        from aaak_provider.temporal_decay import TemporalDecayEngine
        from aaak_provider.context_builder import ContextBuilder, CompressionContext
        
        compressor = AAkCompressor()
        decay = TemporalDecayEngine()
        tier_manager = TierManager(decay_engine=decay)
        builder = ContextBuilder(compressor, tier_manager, decay)
        
        # Simulate raw memories
        raw_memories = [
            ("User identity: Alice, Linux, Python dev", "IDENTITY", "identity"),
            ("Prefers dark mode and vim", "PREF", "preferences"),
            ("Project Lumina is WIP", "PROJ", "projects"),
            ("Discovered AAAK compression", "DISC", "discoveries"),
            ("Auto-sweep: summarized session", "AUTO", "auto"),
        ]
        
        # Compress and assign to tiers
        memories = []
        for content, label, topic in raw_memories:
            compressed = compressor.compress(content, label)
            tier = tier_manager.assign_tier(compressed, label, topic)
            token_est = compressor.estimate_tokens(compressed)
            
            mem = TieredMemory(
                content=compressed,
                tier=tier,
                label=label,
                token_estimate=token_est,
                timestamp="2026-08-06T12:00:00",
                topic=topic
            )
            memories.append(mem)
        
        # Build context
        context = CompressionContext(
            session_id="test",
            max_tokens=1000,
            include_nightstand=True
        )
        
        block = builder.build_context_block(memories, context)
        
        assert block.total_tokens > 0
        assert len(block.tier_breakdown) >= 3  # At least identity, critical, recent
        assert "IDENTITY" in block.content
        assert "PREF" in block.content
        assert "PROJ" in block.content


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_compressor():
    return AAkCompressor()

@pytest.fixture
def sample_tier_manager():
    return TierManager()

@pytest.fixture
def sample_decay_engine():
    return TemporalDecayEngine()

@pytest.fixture
def sample_context_builder():
    return create_context_builder()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])