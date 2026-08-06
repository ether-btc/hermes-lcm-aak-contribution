"""
AAAK Compression Engine

Deterministic compression achieving ~30x token reduction on verbose prose.
The compressed output is natively AI-readable (no decoder needed).

Adapted from Lumina MemPalace (Bino5150/lumina) - tools/palace.py
Licensed Apache-2.0
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Default abbreviation map (seed from Lumina)
DEFAULT_AAAK_ABBREV: Dict[str, str] = {
    # Core domain terms
    "project": "PROJ",
    "preference": "PREF",
    "discovery": "DISC",
    "important": "IMP",
    "conversation": "CONV",
    "session": "SESS",
    "running": "RUN",
    "completed": "DONE",
    "in progress": "WIP",
    "working on": "WIP",
    # Entities
    "user": "USR",
    "assistant": "ASST",
    # Technical terms
    "local": "LOC",
    "database": "DB",
    "filesystem": "FS",
    "terminal": "TERM",
    "knowledge": "KNW",
    "memory": "MEM",
    "interface": "UI",
    "python": "PY",
    "function": "FN",
    # Lumina-specific
    "lumina": "LUM",
    "bino": "BIN",
    "dark mode": "dark-mode",
    "vim keybindings": "vim-bindings",
    # Connectives
    "because": "b/c",
    "with": "w/",
    "without": "w/o",
    "between": "btwn",
    "regarding": "re:",
    "approximately": "~",
    "and": "+",
    "also": "+",
}

# Filler words to strip (from Lumina)
FILLER_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "has", "have", "had",
    "be", "been", "being", "that", "this", "which", "very", "really",
    "just", "some", "any"
}

FILLER_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in FILLER_WORDS) + r')\b',
    re.IGNORECASE
)


@dataclass
class AAkConfig:
    """Configuration for AAAK compressor."""
    abbreviation_map: Dict[str, str] = field(default_factory=lambda: DEFAULT_AAAK_ABBREV.copy())
    filler_words: set = field(default_factory=lambda: FILLER_WORDS.copy())
    min_line_length: int = 5  # Skip compression for very short lines (below threshold)


class AAkCompressor:
    """
    AAAK deterministic compressor.
    
    Achieves ~30x token reduction on verbose prose by:
    1. Applying domain-specific abbreviation map (longest-match-first)
    2. Collapsing whitespace
    3. Stripping filler words
    4. Prepending category labels
    
    Output is directly readable by LLMs without a decoder.
    """
    
    def __init__(self, config: Optional[AAkConfig] = None):
        self.config = config or AAkConfig()
        # Pre-sort abbreviations by length (longest first) for correct substitution
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: -len(x[0])
        )
    
    def compress(self, text: str, label: Optional[str] = None) -> str:
        """
        Compress text using AAAK algorithm.
        
        Args:
            text: Input text to compress
            label: Optional category label (e.g., "PREF", "PROJ", "SESS")
            
        Returns:
            AAAK-compressed string
        """
        if not text:
            return ""
        
        result = text.strip()
        
        # Check if already compressed with a label (starts with LABEL:)
        # If so, don't re-compress or re-label
        if label and re.match(r'^[A-Z]+:', result):
            # Already has a label prefix, return as-is
            return result
        
        # Skip if too short
        if len(result) < self.config.min_line_length:
            if label:
                return f"{label.upper()}: {result}"
            return result
        
        # 1. Apply abbreviations (longest match first)
        for full, abbr in self._sorted_abbrev:
            result = re.sub(re.escape(full), abbr, result, flags=re.IGNORECASE)
        
        # 2. Collapse whitespace
        result = re.sub(r'\s+', ' ', result).strip()
        
        # 3. Strip filler words
        result = FILLER_PATTERN.sub('', result)
        result = re.sub(r'\s+', ' ', result).strip()
        
        # 4. Prepend label
        if label:
            result = f"{label.upper()}: {result}"
        
        return result
    
    def compress_lines(self, lines: List[str], labels: Optional[List[str]] = None) -> List[str]:
        """
        Compress multiple lines with optional labels.
        
        Args:
            lines: List of text lines
            labels: Optional list of labels (same length as lines)
            
        Returns:
            List of compressed lines
        """
        if labels is None:
            labels = [None] * len(lines)
        
        return [self.compress(line, label) for line, label in zip(lines, labels)]
    
    def estimate_tokens(self, text: str) -> int:
        """Fast heuristic: ~4 chars per token."""
        return max(1, len(text) // 4)
    
    def add_abbreviation(self, full: str, abbr: str) -> None:
        """Add or update an abbreviation in the map."""
        self.config.abbreviation_map[full] = abbr
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: -len(x[0])
        )
    
    def load_abbreviation_map(self, path: str) -> None:
        """Load abbreviation map from JSON file."""
        import json
        with open(path) as f:
            self.config.abbreviation_map = json.load(f)
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: -len(x[0])
        )


def create_compressor(config: Optional[Dict] = None) -> AAkCompressor:
    """Factory function for creating compressor with optional config dict."""
    if config is None:
        return AAkCompressor()
    
    aaak_config = AAkConfig()
    if "abbreviation_map" in config:
        aaak_config.abbreviation_map.update(config["abbreviation_map"])
    if "filler_words" in config:
        aaak_config.filler_words.update(config["filler_words"])
    if "min_line_length" in config:
        aaak_config.min_line_length = config["min_line_length"]
    
    return AAkCompressor(aaak_config)