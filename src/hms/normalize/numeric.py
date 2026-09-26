"""Restore numerals and symbols mangled by MinerU math-mode spacing.

MinerU emits math spans with a space between every glyph, so ``10^{12}``
arrives as ``$\\{ 1 0 \\} ^ { 1 2 }$`` and ``99.999%`` as
``$9 9 . 9 9 9 \\%$``. A chunk carrying that text is unreachable by any
embedding model: the digits, the decimal point and the exponent are all lost
during tokenization, which is a primary reason the reference pipeline stalls
below the accuracy gate.

Only the inside of ``$...$`` spans is rewritten; prose is returned verbatim.
Span detection is escape aware, so a literal ``\\$`` inside a span (as MinerU
writes for currency amounts) neither terminates the span early nor causes two
adjacent spans to be paired incorrectly. Prose is therefore never modified, not
even its whitespace.

The rewrite is a fixed point iteration over an ordered rule table so that one
pass can enable another, for example unwrapping ``\\mathrm { k g }`` before
collapsing the letters.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

MATH_SEGMENT = re.compile(r"\$((?:[^$\\]|\\.)*?)\$", re.DOTALL)

_MAX_PASSES = 8

_FONT_COMMANDS = "mathrm|mathsf|mathbf|mathcal|boldsymbol|mathit|text|textrm|textit|texttt"

_WORD_SPACE_COMMANDS = re.compile(
    r"\\(?:quad|qquad|thinspace|enspace|left|right|bigl|bigr|Bigl|Bigr|"
    r"displaystyle|textstyle)\b\s*"
)
# `\left.` and `\right.` are invisible delimiters; dropping only the command
# would leave a stray period behind.
_INVISIBLE_DELIMITER = re.compile(r"\\(?:left|right)\s*\.")
_SYMBOL_SPACE_COMMANDS = re.compile(r"\\[!,;:]\s*")
_ESCAPED_SPACE = re.compile(r"\\ ")

_NON_BREAKING_SPACE = re.compile("~")

_SYMBOLS = {
    r"\Leftrightarrow": "⇔",
    r"\longrightarrow": "→",
    r"\Rightarrow": "⇒",
    r"\rightarrow": "→",
    r"\leftarrow": "←",
    r"\approx": "≈",
    r"\simeq": "≃",
    r"\prime": "′",
    r"\times": "×",
    r"\cdot": "·",
    r"\circ": "°",
    r"\Delta": "Δ",
    r"\Omega": "Ω",
    r"\alpha": "α",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\theta": "θ",
    r"\kappa": "κ",
    r"\lambda": "λ",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\rho": "ρ",
    r"\phi": "φ",
    r"\beta": "β",
    r"\eta": "η",
    r"\pi": "π",
    r"\mu": "μ",
    r"\nu": "ν",
    r"\geq": "≥",
    r"\leq": "≤",
    r"\neq": "≠",
    r"\pm": "±",
    r"\mp": "∓",
    r"\ge": "≥",
    r"\le": "≤",
    r"\sim": "~",
    r"\ell": "ℓ",
    r"\langle": "⟨",
    r"\rangle": "⟩",
    r"\in": "∈",
    r"\%": "%",
    r"\&": "&",
    r"\#": "#",
}


def _build_symbol_pattern() -> re.Pattern[str]:
    """Alternation over symbol commands, longest first, with word guards."""
    parts = []
    for command in sorted(_SYMBOLS, key=len, reverse=True):
        escaped = re.escape(command)
        parts.append(escaped + r"\b" if command[-1].isalpha() else escaped)
    return re.compile("|".join(parts))


def _replace_symbol(match: re.Match[str]) -> str:
    return _SYMBOLS[match.group(0)]


def _join_letters(match: re.Match[str]) -> str:
    return match.group(0).replace(" ", "")


Replacement = str | Callable[[re.Match[str]], str]

_RULES: tuple[tuple[str, re.Pattern[str], Replacement], ...] = (
    ("invisible_delimiter", _INVISIBLE_DELIMITER, ""),
    ("symbol_space_command", _SYMBOL_SPACE_COMMANDS, ""),
    ("word_space_command", _WORD_SPACE_COMMANDS, ""),
    ("escaped_space", _ESCAPED_SPACE, " "),
    ("escaped_brace", re.compile(r"\\([{}])"), r"\1"),
    ("font_unwrap", re.compile(rf"\\(?:{_FONT_COMMANDS})\s*\{{([^{{}}]*)\}}"), r"\1"),
    ("superscript_glue", re.compile(r"\s*\^\s*"), "^"),
    ("subscript_glue", re.compile(r"\s*_\s*"), "_"),
    ("open_bracket_glue", re.compile(r"([(\[])\s+"), r"\1"),
    ("close_bracket_glue", re.compile(r"\s+([)\]])"), r"\1"),
    ("brace_trim_open", re.compile(r"\{\s+"), "{"),
    ("brace_trim_close", re.compile(r"\s+\}"), "}"),
    ("digit_glue_left", re.compile(r"(?<=\d)\s+(?=[\d.,])"), ""),
    ("digit_glue_right", re.compile(r"(?<=[\d.,])\s+(?=\d)"), ""),
    ("sign_glue", re.compile(r"(?<=[-+])\s+(?=\d)"), ""),
    ("percent_glue", re.compile(r"\s+(?=%)"), ""),
    ("quote_trim", re.compile(r'"\s*([^"]*?)\s*"'), r'"\1"'),
    ("relation_command", re.compile(r"\s*\\\s*([=<>])\s*"), r" \1 "),
    (
        "letter_run",
        re.compile(r"(?<![A-Za-z])([A-Za-z])(?: ([A-Za-z]))+(?![A-Za-z])"),
        _join_letters,
    ),
    ("symbol_map", _build_symbol_pattern(), _replace_symbol),
    ("brace_unwrap", re.compile(r"\{([^\\{}\s]{1,12})\}"), r"\1"),
    ("collapse_space", re.compile(r"\s{2,}"), " "),
)


def normalize_math(body: str, stats: Counter[str] | None = None) -> str:
    """Rewrite the inner text of a single ``$...$`` span."""
    current = _NON_BREAKING_SPACE.sub("", body)
    for _ in range(_MAX_PASSES):
        updated = current
        for name, pattern, replacement in _RULES:
            updated, count = pattern.subn(replacement, updated)
            if count and stats is not None:
                stats[name] += count
        if updated == current:
            break
        current = updated
    return current.strip()


def normalize_text(text: str, stats: Counter[str] | None = None) -> str:
    """Normalize every math span in ``text``, leaving prose untouched."""
    if not isinstance(text, str) or "$" not in text:
        return text

    def _rewrite(match: re.Match[str]) -> str:
        body = normalize_math(match.group(1), stats)
        if not body:
            return match.group(0)
        return f"${body}$"

    return MATH_SEGMENT.sub(_rewrite, text)
