"""Text normalization utilities for the summarization pipeline.

Conservative by design: removes only clearly problematic characters
(invisible/garbage Unicode, PDF extraction artifacts) without destroying
technical content, math notation, or markdown structure.
"""

from __future__ import annotations

import re
import unicodedata


# ── Regex patterns ────────────────────────────────────────────────────────────

# Zero-width and invisible Unicode characters that carry no content
_INVISIBLE_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f"   # zero-width spaces / direction marks
    r"\u202a-\u202e"                       # directional embedding/override
    r"\u2060-\u2064"                       # word joiners / invisible math ops
    r"\ufeff"                              # BOM
    r"\u00ad]"                             # soft hyphen
)

# ASCII control characters (excluding \t, \n, \r which are legitimate)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Unicode replacement character and common "garbage box" characters that
# appear when PDF font encoding fails and can't be recovered.
# Note: U+25A1 (WHITE SQUARE □) and U+25A0 (BLACK SQUARE ■) can appear
# legitimately as bullets — only remove U+FFFD (REPLACEMENT CHARACTER).
_REPLACEMENT_CHAR = re.compile(r"\ufffd")

# Null bytes that sometimes leak through PDF extraction
_NULL_BYTES = re.compile(r"\x00+")

# PDF hyphenated line-break artifact: "algo-\nritmo" → "algoritmo"
# Only when hyphen is preceded and followed by a word character.
_HYPHEN_LINE_BREAK = re.compile(r"(\w)-\n(\w)")

# Excessive horizontal whitespace (3+ spaces/tabs collapse to one space)
_MULTI_SPACES = re.compile(r"[ \t]{3,}")

# More than 2 consecutive blank lines
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")

# Lines with only whitespace characters
_WHITESPACE_ONLY_LINE = re.compile(r"^[ \t]+$", re.MULTILINE)

# Unicode Private Use Area characters (U+E000–U+F8FF, Supplementary PUA planes).
# PDFs often use PUA codepoints for custom font glyphs that cannot be recovered
# as readable text. These are unambiguously garbage in extracted text.
_PUA_CHARS = re.compile(r"[\ue000-\uf8ff\U000f0000-\U000fffff\U00100000-\U0010ffff]")

# Unicode typographic ligatures commonly produced by PDF font substitution.
# Mapping to their ASCII equivalents preserves readability for LLM processing.
_LIGATURE_MAP: dict[str, str] = {
    "\ufb00": "ff",   # ﬀ  LATIN SMALL LIGATURE FF
    "\ufb01": "fi",   # ﬁ  LATIN SMALL LIGATURE FI
    "\ufb02": "fl",   # ﬂ  LATIN SMALL LIGATURE FL
    "\ufb03": "ffi",  # ﬃ  LATIN SMALL LIGATURE FFI
    "\ufb04": "ffl",  # ﬄ  LATIN SMALL LIGATURE FFL
    "\ufb05": "st",   # ﬅ  LATIN SMALL LIGATURE LONG S T
    "\ufb06": "st",   # ﬆ  LATIN SMALL LIGATURE ST
}
_LIGATURE_PATTERN = re.compile("|".join(re.escape(k) for k in _LIGATURE_MAP))

# Mathematical Alphanumeric Symbols block (U+1D400–U+1D7FF).
# These are mathematical italic/bold styled letters that render poorly in
# plain text and Markdown (e.g., 𝑇, 𝑡, 𝛼). NFKC normalization maps each
# one to its closest ASCII or Greek base character (e.g., 𝑇 → T, 𝛼 → α).
_MATH_ALNUM_RE = re.compile(r"[\U0001D400-\U0001D7FF]")

# Sinhala script block (U+0D80–U+0DFF).
# Some PDF extractors emit Sinhala codepoints as artifacts when the font
# encoding fails for superscript/subscript markers. These characters are
# never valid in Portuguese or English technical documents.
_SINHALA_RE = re.compile(r"[\u0D80-\u0DFF]")


# ── Public API ────────────────────────────────────────────────────────────────

def _normalize_math_chars(text: str) -> str:
    """Normalize mathematical alphanumeric symbols and remove Sinhala artifacts.

    Applies NFKC normalization to each character in the Mathematical
    Alphanumeric Symbols block (U+1D400–U+1D7FF) so that styled variants
    collapse to their base letters: 𝑇 → T, 𝑡 → t, 𝛼 → α, 𝑅 → R, etc.

    Also strips Sinhala characters (U+0D80–U+0DFF) which appear as PDF
    extraction artifacts in some academic papers.

    Safe: operates only on the targeted Unicode blocks; all other characters
    pass through unchanged.
    """
    text = _SINHALA_RE.sub("", text)
    text = _MATH_ALNUM_RE.sub(
        lambda m: unicodedata.normalize("NFKC", m.group(0)), text
    )
    return text


def _expand_ligatures(text: str) -> str:
    """Replace Unicode typographic ligatures with their ASCII equivalents.

    This is safe because these ligatures carry no semantic distinction from
    their component letters — they are purely typographic glyphs used in
    typesetting that appear when PDFs are extracted with certain font encodings.
    """
    return _LIGATURE_PATTERN.sub(lambda m: _LIGATURE_MAP[m.group(0)], text)


def clean_chunk_text(text: str) -> str:
    """Clean extracted chunk text before passing to the LLM.

    Conservative: preserves technical content, math symbols, and markdown.
    Only removes characters that are unambiguously garbage or harmful.
    """
    if not text:
        return text

    # 1. NFC normalization — ensures consistent representation of accented chars
    text = unicodedata.normalize("NFC", text)

    # 2. Remove null bytes
    text = _NULL_BYTES.sub("", text)

    # 3. Remove invisible/zero-width characters
    text = _INVISIBLE_CHARS.sub("", text)

    # 4. Remove ASCII control characters (preserve whitespace: \t \n \r)
    text = _CONTROL_CHARS.sub("", text)

    # 5. Remove Unicode replacement character (shows as □ in some renderers)
    text = _REPLACEMENT_CHAR.sub("", text)

    # 6. Remove Private Use Area characters (custom PDF glyphs, unrecoverable)
    text = _PUA_CHARS.sub("", text)

    # 7. Normalize mathematical alphanumeric symbols (𝑇→T, 𝛼→α) and remove Sinhala artifacts
    text = _normalize_math_chars(text)

    # 8. Expand typographic ligatures (ﬁ → fi, ﬂ → fl, etc.)
    text = _expand_ligatures(text)

    # 9. Fix PDF hyphenated line breaks (word split at column edge)
    text = _HYPHEN_LINE_BREAK.sub(r"\1\2", text)

    # 10. Collapse excessive horizontal whitespace
    text = _MULTI_SPACES.sub(" ", text)

    # 11. Remove whitespace-only lines (keep blank lines for paragraph separation)
    text = _WHITESPACE_ONLY_LINE.sub("", text)

    # 12. Normalize excessive blank lines
    text = _MULTI_BLANK_LINES.sub("\n\n", text)

    return text.strip()


def clean_summary_output(text: str) -> str:
    """Light cleaning of LLM-generated summary text.

    Lighter touch than clean_chunk_text — LLM output is generally cleaner.
    Mainly normalizes whitespace and removes any leaked invisible characters.
    """
    if not text:
        return text

    # 1. NFC normalization
    text = unicodedata.normalize("NFC", text)

    # 2. Remove invisible characters
    text = _INVISIBLE_CHARS.sub("", text)

    # 3. Remove replacement character
    text = _REPLACEMENT_CHAR.sub("", text)

    # 4. Normalize mathematical alphanumeric symbols and strip Sinhala artifacts
    text = _normalize_math_chars(text)

    # 5. Normalize excessive blank lines (max 2 consecutive)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)

    # 6. Remove trailing whitespace per line (keeps markdown clean)
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()
