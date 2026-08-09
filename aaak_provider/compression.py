"""
AAAK Compression Engine

Deterministic compression; the historical ~30x reduction is an unverified target.
The compressed output is natively AI-readable (no decoder needed).

Adapted from Lumina MemPalace (Bino5150/lumina) - tools/palace.py
Licensed Apache-2.0
"""

import json
import re
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Dict, List, Optional


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


def _validate_abbreviation_map(abbreviation_map: Any) -> Dict[str, str]:
    """Validate and copy an abbreviation map before it reaches regex building."""
    if not isinstance(abbreviation_map, Mapping):
        raise TypeError("abbreviation_map must be a mapping")
    if not abbreviation_map:
        raise ValueError("abbreviation_map must not be empty")

    validated: Dict[str, str] = {}
    normalized_keys = set()
    for full, abbr in abbreviation_map.items():
        if not isinstance(full, str) or not isinstance(abbr, str):
            raise TypeError("abbreviation_map keys and values must be strings")
        if not full.strip() or not abbr.strip():
            raise ValueError("abbreviation_map keys and values must be non-empty")
        if "\n" in full or "\r" in full or "\n" in abbr or "\r" in abbr:
            raise ValueError("abbreviation_map keys and values must be single-line")
        normalized = full.casefold()
        if normalized in normalized_keys:
            raise ValueError("abbreviation_map keys must be unique case-insensitively")
        normalized_keys.add(normalized)
        validated[full] = abbr
    return validated


def _validate_filler_words(filler_words: Any) -> set[str]:
    """Validate filler words while allowing an explicit empty set."""
    if isinstance(filler_words, (str, bytes)):
        raise TypeError("filler_words must be an iterable of strings")
    try:
        words = set(filler_words)
    except TypeError as exc:
        raise TypeError("filler_words must be an iterable of strings") from exc
    if any(not isinstance(word, str) for word in words):
        raise TypeError("filler_words must contain only strings")
    if any(not word.strip() or "\n" in word or "\r" in word for word in words):
        raise ValueError("filler_words must contain non-empty single-line strings")
    return words


def _validate_min_line_length(min_line_length: Any) -> int:
    if isinstance(min_line_length, bool) or not isinstance(min_line_length, int):
        raise TypeError("min_line_length must be an integer")
    if min_line_length < 0:
        raise ValueError("min_line_length must be non-negative")
    return min_line_length


def _validate_config(config: AAkConfig) -> None:
    _validate_abbreviation_map(config.abbreviation_map)
    _validate_filler_words(config.filler_words)
    _validate_min_line_length(config.min_line_length)


class AAkCompressor:
    """
    AAAK deterministic compressor.
    
    Applies deterministic transformations to prose by:
    1. Applying domain-specific abbreviation map (longest-match-first)
    2. Collapsing whitespace
    3. Stripping filler words
    4. Prepending category labels
    
    Output is directly readable by LLMs without a decoder.
    """
    
    def __init__(self, config: Optional[AAkConfig] = None):
        self.config = config if config is not None else AAkConfig()
        if not isinstance(self.config, AAkConfig):
            raise TypeError("config must be an AAkConfig")
        _validate_config(self.config)
        # Pre-sort abbreviations by length (longest first) for correct substitution
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: (-len(x[0]), x[0].casefold(), x[0])
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

        # Protect literals whose spelling is meaningful and must survive lossy
        # compression. Placeholders contain underscores, so abbreviation and
        # filler-word boundary rules cannot rewrite them.
        protected_literals = []

        def protect(match: re.Match[str]) -> str:
            protected_literals.append(match.group(0))
            return f"__AAAK_LITERAL_{len(protected_literals) - 1}__"

        literal_pattern = re.compile(
            r'`[^`]+`|"(?:\\.|[^"\\])*"|https?://[^\s`<>()\[\]{}\'\"]+|/[A-Za-z0-9._~+%/@-]+'
        )
        result = literal_pattern.sub(protect, result)
        
        # 1. Apply abbreviations (longest match first)
        for full, abbr in self._sorted_abbrev:
            # Match words/phrases, not substrings inside identifiers or words
            # (e.g. "and" must not rewrite "candy").
            pattern = rf"(?<!\w){re.escape(full)}(?!\w)"
            result = re.sub(pattern, abbr, result, flags=re.IGNORECASE)
        
        # 2. Collapse whitespace
        result = re.sub(r'\s+', ' ', result).strip()
        
        # 3. Strip filler words
        filler_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(w) for w in self.config.filler_words) + r')\b',
            re.IGNORECASE,
        )
        result = filler_pattern.sub('', result)
        result = re.sub(r'\s+', ' ', result).strip()
        
        # 4. Prepend label
        if label:
            result = f"{label.upper()}: {result}"

        for index, literal in enumerate(protected_literals):
            result = result.replace(f"__AAAK_LITERAL_{index}__", literal)
        
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
        candidate = dict(self.config.abbreviation_map)
        candidate[full] = abbr
        self.config.abbreviation_map = _validate_abbreviation_map(candidate)
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: (-len(x[0]), x[0].casefold(), x[0])
        )
    
    def load_abbreviation_map(self, path: str) -> None:
        """Load abbreviation map from JSON file."""
        with open(path) as f:
            loaded = _validate_abbreviation_map(json.load(f))
        self.config.abbreviation_map = loaded
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: (-len(x[0]), x[0].casefold(), x[0])
        )


def create_compressor(config: Optional[Dict] = None) -> AAkCompressor:
    """Factory function for creating compressor with optional config dict."""
    if config is None:
        return AAkCompressor()
    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")
    unknown = set(config) - {"abbreviation_map", "filler_words", "min_line_length"}
    if unknown:
        raise ValueError(f"unknown compressor configuration keys: {sorted(unknown)!r}")

    aaak_config = AAkConfig()
    if "abbreviation_map" in config:
        additions = _validate_abbreviation_map(config["abbreviation_map"])
        aaak_config.abbreviation_map.update(additions)
    if "filler_words" in config:
        aaak_config.filler_words.update(_validate_filler_words(config["filler_words"]))
    if "min_line_length" in config:
        aaak_config.min_line_length = _validate_min_line_length(config["min_line_length"])
    
    return AAkCompressor(aaak_config)