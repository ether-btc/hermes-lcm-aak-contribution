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
from typing import Any, Callable, Dict, List, Optional


# Default abbreviation map (seed from Lumina)
DEFAULT_AAAK_ABBREV: Dict[str, str] = {
    # --- Multi-word phrases (highest value: collapse N tokens into 0-1) ---
    "the user prefers": "",
    "the user is": "",
    "the user has": "",
    "the user asked": "",
    "the user wants": "",
    "the user is working on": "USR WIP",
    "the user asked about": "USR asked",
    "the user wants to know": "USR wants",
    "the project is": "",
    "the local database": "LOC DB",
    "the assistant explained": "ASST explained",
    "the bot": "BOT",
    "because the project is": "b/c PROJ",
    "and the user": "+ USR",
    "working on": "WIP",
    "in progress": "WIP",

    # --- Domain-specific phrases (user's corpus) ---
    "compression ratio": "comp_ratio",
    "trading bot": "tradebot",
    "session summary": "SESS-SUM",
    "research corpus": "RSRCH-CRP",
    "growing research corpus": "growing RSRCH-CRP",
    "token count": "tok_cnt",
    "should be grounded": "must ground",
    "capital preservation": "cap_pres",
    "opportunity preservation": "opp_pres",
    "no-loss constraint": "no-loss",
    "compression algorithm": "comp_alg",
    "deterministic scheme": "determ_scheme",
    "tight deadline": "tight-deadline",
    "dark mode": "dark-mode",
    "vim keybindings": "vim-bindings",
    "lossless store": "lossless_store",
    "rolling summary": "roll_sum",
    "summary model": "sum_model",
    "context block": "ctx_blk",
    "memory item": "mem_item",
    "conversation history": "conv_hist",
    "externalized payload": "ext_payload",
    "episodic memory": "epi_mem",
    "working memory": "work_mem",
    "semantic search": "sem_search",
    "token reduction": "tok_reduce",
    "provider registry": "prov_reg",
    "config file": "cfg_file",
    "test suite": "test_suite",
    "benchmark report": "bench_rpt",
    "compression engine": "comp_eng",
    "session start": "SESS-start",
    "session end": "SESS-end",
    "memory database": "mem_DB",
    "knowledge graph": "know_graph",
    "fact triple": "fact_triple",
    "subject key": "subj_key",
    "predicate key": "pred_key",

    # --- Core domain terms ---
    "project": "PROJ",
    "preference": "PREF",
    "discovery": "DISC",
    "important": "IMP",
    "conversation": "CONV",
    "session": "SESS",
    "running": "RUN",
    "completed": "DONE",

    # --- Entities ---
    "user": "USR",
    "assistant": "ASST",

    # --- Technical terms ---
    "local": "LOC",
    "database": "DB",
    "filesystem": "FS",
    "terminal": "TERM",
    "knowledge": "KNW",
    "memory": "MEM",
    "interface": "UI",
    "python": "PY",
    "function": "FN",

    # --- Lumina-specific ---
    "lumina": "LUM",
    "bino": "BIN",

    # --- Connectives ---
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
    # --- M2.5: expansion guard ---
    # When True (default), compress() returns the original text if the chosen
    # tokenizer reports that compression would *increase* token count.  This is
    # the load-bearing fix for the 0.95x cl100k_base expansion documented in
    # STATUS.md.
    expansion_guard: bool = True
    # Tokenizer callable: str -> int.  Defaults to the package heuristic
    # (max(1, len(text)//4)).  Callers can inject tiktoken or a real model
    # tokenizer so the guard is measured against the target model.
    token_counter: Optional[Callable[[str], int]] = None
    # Minimum input length (in tokens) below which we skip compression entirely.
    # Short messages rarely compress and the label overhead is proportionally high.
    min_input_tokens: int = 8


def _validate_abbreviation_map(abbreviation_map: Any) -> Dict[str, str]:
    """Validate and copy an abbreviation map before it reaches regex building.

    Empty string values are allowed — they mean "delete this phrase entirely".
    """
    if not isinstance(abbreviation_map, Mapping):
        raise TypeError("abbreviation_map must be a mapping")
    if not abbreviation_map:
        raise ValueError("abbreviation_map must not be empty")

    validated: Dict[str, str] = {}
    normalized_keys = set()
    for full, abbr in abbreviation_map.items():
        if not isinstance(full, str) or not isinstance(abbr, str):
            raise TypeError("abbreviation_map keys and values must be strings")
        if not full.strip():
            raise ValueError("abbreviation_map keys must be non-empty")
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
        # Build a single regex alternation for all abbreviations.
        # This prevents overlapping matches where one substitution
        # creates a new match for a shorter pattern.
        # Deduplicate by lowercase full key to avoid regex alternation issues.
        seen = set()
        deduped = []
        for full, _ in self._sorted_abbrev:
            lower = full.casefold()
            if lower not in seen:
                seen.add(lower)
                deduped.append(full)
        escaped = [re.escape(full) for full in deduped]
        self._abbrev_pattern = re.compile(
            rf"(?<!\w)({'|'.join(escaped)})(?!\w)",
            re.IGNORECASE
        )
        # Build a lookup from lowercase full -> replacement
        self._abbrev_lookup = {full.casefold(): abbr for full, abbr in self._sorted_abbrev}

    def compress(self, text: str, label: Optional[str] = None) -> str:
        """
        Compress text using AAAK algorithm.

        Args:
            text: Input text to compress
            label: Optional category label (e.g., "PREF", "PROJ", "SESS")

        Returns:
            AAAK-compressed string.  If the expansion_guard is enabled and the
            chosen tokenizer reports that compression would *increase* token
            count, the original text is returned instead.  This prevents the
            0.95x expansion seen on structured content (URLs, JSON, logs).
        """
        if not text:
            return ""

        result = text.strip()

        # Check if already compressed with a label (starts with LABEL:)
        # If so, don't re-compress or re-label
        if label and re.match(r'^[A-Z]+:', result):
            return result

        # Skip if too short
        if len(result) < self.config.min_line_length:
            if label:
                return f"{label.upper()}: {result}"
            return result

        # M2.5 content-type classifier — skip compression on structured
        # content where abbreviation cannot help and risks corruption.
        # This is the second lever for preventing expansion: code, JSON,
        # URLs, logs, shell commands, and identifiers should pass through.
        # When a label is provided, we still skip clearly structured content
        # (JSON, code blocks, URLs) but allow abbreviation on labeled prose.
        if label is None:
            if self._is_structured(result):
                return result
        else:
            # With a label, only skip unambiguously structured content
            if self._is_unambiguously_structured(result):
                return result

        # Protect literals whose spelling is meaningful and must survive lossy
        # compression. Placeholders contain underscores, so abbreviation and
        # filler-word boundary rules cannot rewrite them.
        protected_literals = []

        def protect(match: re.Match[str]) -> str:
            protected_literals.append(match.group(0))
            return f"__AAAK_LITERAL_{len(protected_literals) - 1}__"

        literal_pattern = re.compile(
            r'`[^`]+`|"[^"]*"|https?://\S+|(?:^|/)[A-Za-z0-9._~+%-]+(?:/[A-Za-z0-9._~+%-]+)+'
        )
        result = literal_pattern.sub(protect, result)

        # 1. Apply abbreviations (longest match first via single-pass alternation)
        def replace_match(m: re.Match[str]) -> str:
            matched_text = m.group(0)
            replacement = self._abbrev_lookup[matched_text.casefold()]
            return replacement

        result = self._abbrev_pattern.sub(replace_match, result)

        # Collapse whitespace that may result from empty replacements
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

        # M2.5 expansion guard — return original if compression strictly
        # increased token count.  Equal token count is allowed (character
        # reduction still creates headroom for other content).  This is the
        # load-bearing fix for the 0.95x cl100k_base expansion documented in
        # STATUS.md.
        #
        # With a label, we tolerate expansion up to 2 tokens (label overhead
        # is ~2 tokens and the semantic structure is valuable).  Beyond that,
        # the compression is doing real harm.
        if self.config.expansion_guard:
            counter: Callable[[str], int] = self.config.token_counter or self.estimate_tokens
            compressed_tokens = counter(result)
            original_tokens = counter(text)
            if label is None:
                # Unlabeled: return original only if compression failed to
                # reduce character count.  Equal token count with fewer
                # characters is still a win (creates headroom, improves
                # structure for the reader).
                if len(result) >= len(text):
                    return text
            else:
                # Labeled: tolerate up to 2 tokens of label overhead
                if compressed_tokens > original_tokens + 2:
                    return text

        return result

    def _is_structured(self, text: str) -> bool:
        """Return True when text is structured content that should pass through.

        Structured content (code, JSON, URLs, logs, shell commands, identifiers)
        has high information density and low redundancy.  Abbreviation mapping
        cannot compress it, and may corrupt it.  The expansion guard handles
        the general case, but this catches specific content types early for
        speed and predictability.
        """
        if not text:
            return False

        stripped = text.strip()

        # JSON: starts with { or [ and ends with } or ]
        if (stripped.startswith('{') and stripped.endswith('}')) or \
           (stripped.startswith('[') and stripped.endswith(']')):
            return True

        # Code blocks: starts/ends with ```
        if stripped.startswith('```') and stripped.endswith('```'):
            return True

        # URLs: high ratio of non-alphanumeric to alphanumeric
        if re.match(r'^https?://', stripped):
            return True

        # Shell commands: starts with common command prefixes
        if re.match(r'^(python|pip|uv|git|ls|cd|rm|cp|mv|curl|wget|ssh|sudo|apt|docker|npm|node|go|rust|cargo|make|cmake|pytest|echo|cat|grep|rg|find|awk|sed|jq)\s', stripped):
            return True

        # Identifiers/paths: mostly non-letter characters
        alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
        if alpha_ratio < 0.5 and len(text) > 20:
            return True

        return False

    def _is_unambiguously_structured(self, text: str) -> bool:
        """Return True when text is unambiguously structured (JSON, code blocks, URLs).

        For labeled compression, we only skip content that is clearly not prose.
        Ambiguous cases (short text, paths, commands) are allowed through because
        the label provides value and the abbreviation can still help.
        """
        if not text:
            return False

        stripped = text.strip()

        # JSON
        if (stripped.startswith('{') and stripped.endswith('}')) or \
           (stripped.startswith('[') and stripped.endswith(']')):
            return True

        # Code blocks
        if stripped.startswith('```') and stripped.endswith('```'):
            return True

        # Pure URLs
        if re.match(r'^https?://', stripped):
            return True

        return False

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

    def _recompile(self) -> None:
        """Recompile the abbreviation regex and lookup after map changes."""
        seen = set()
        deduped = []
        for full_key, _ in self._sorted_abbrev:
            lower = full_key.casefold()
            if lower not in seen:
                seen.add(lower)
                deduped.append(full_key)
        escaped = [re.escape(full_key) for full_key in deduped]
        self._abbrev_pattern = re.compile(
            rf"(?<!\w)({'|'.join(escaped)})(?!\w)",
            re.IGNORECASE
        )
        self._abbrev_lookup = {full_key.casefold(): abbr for full_key, abbr in self._sorted_abbrev}

    def add_abbreviation(self, full: str, abbr: str) -> None:
        """Add or update an abbreviation in the map."""
        candidate = dict(self.config.abbreviation_map)
        candidate[full] = abbr
        self.config.abbreviation_map = _validate_abbreviation_map(candidate)
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: (-len(x[0]), x[0].casefold(), x[0])
        )
        self._recompile()

    def load_abbreviation_map(self, path: str) -> None:
        """Load abbreviation map from JSON file."""
        with open(path) as f:
            loaded = _validate_abbreviation_map(json.load(f))
        self.config.abbreviation_map = loaded
        self._sorted_abbrev = sorted(
            self.config.abbreviation_map.items(),
            key=lambda x: (-len(x[0]), x[0].casefold(), x[0])
        )
        self._recompile()


def create_compressor(config: Optional[Dict] = None) -> AAkCompressor:
    """Factory function for creating compressor with optional config dict."""
    if config is None:
        return AAkCompressor()
    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")
    unknown = set(config) - {"abbreviation_map", "filler_words", "min_line_length",
                              "expansion_guard", "token_counter", "min_input_tokens"}
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
    if "expansion_guard" in config:
        aaak_config.expansion_guard = bool(config["expansion_guard"])
    if "token_counter" in config:
        aaak_config.token_counter = config["token_counter"]
    if "min_input_tokens" in config:
        aaak_config.min_input_tokens = _validate_min_line_length(config["min_input_tokens"])

    return AAkCompressor(aaak_config)
