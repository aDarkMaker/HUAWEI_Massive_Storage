"""Tests for the MinerU math-span normalizer."""

from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path

from hms.normalize import (
    is_blank_block,
    normalize_math,
    normalize_text,
    resolve_image_path,
)

SPLIT_DIGITS = [
    (r"$\{ 1 0 \} ^ { 1 2 }$", r"$10^12$"),
    (r"$1 0 ^ { 5 }$", r"$10^5$"),
    (r"$1 0 ^ { - 2 }$", r"$10^-2$"),
    (r"$1 , 2 0 0$", r"$1,200$"),
    (r"$0 . 0 0 0 0 1 \%$", r"$0.00001%$"),
    (r"$9 9 . 9 9 9 \%$", r"$99.999%$"),
    (r"$3 0 . 0 \%$", r"$30.0%$"),
]

LATEX_WRAPPERS = [
    (r"$6 8 . 5 3 \pm 6 . 9 9 \mathrm { k g }$", "$68.53 \u00b1 6.99 kg$"),
    (r"$( 2 0 \mathsf { H z } )$", "$(20 Hz)$"),
    (r"$( \mathsf { p } { < } 0 . 0 0 1$", "$(p < 0.001$"),
    (r"${ < } 4 5$", "$< 45$"),
    (r"$9 0 ^ { \circ }$", "$90^\u00b0$"),
]

SYMBOLS_AND_RELATIONS = [
    (r"$2 0 . 1 5 \pm 3 . 2 9$", "$20.15 \u00b1 3.29$"),
    (r"$1 1 \ = \ 2 1$", "$11 = 21$"),
    (r"$\alpha \leq \beta$", "$\u03b1 \u2264 \u03b2$"),
]

PROSE_AND_LAYOUT = [
    ('$A g e < " 4 5 "$', '$Age < "45"$'),
    (r"$( p < 0 . 0 5$", "$(p < 0.05$"),
    (
        r"The segment $\mathrm { ~ O ~ } \Rightarrow \mathrm { ~ B ~ }$ translates",
        "The segment $O \u21d2 B$ translates",
    ),
    (r"prose $3 0 . 0 \%$ and $1 , 2 0 0$ units", "prose $30.0%$ and $1,200$ units"),
]

ESCAPED_DOLLAR = [
    (r"costs $\$ 2 8$ USD in total", r"costs $\$ 28$ USD in total"),
    (r"between $\$ 1 0$ and $\$ 2 0$ today", r"between $\$ 10$ and $\$ 20$ today"),
]

ALL_CASES = (
    SPLIT_DIGITS + LATEX_WRAPPERS + SYMBOLS_AND_RELATIONS + PROSE_AND_LAYOUT + ESCAPED_DOLLAR
)

NO_MATH_INPUTS = (
    "no math here at all",
    "A table caption with 1,200 units and 45% growth.",
    "",
)


class NormalizeTextTest(unittest.TestCase):
    """Cover the rules that repair MinerU's per-glyph math spacing."""

    def test_split_digits_are_rejoined(self) -> None:
        for raw, expected in SPLIT_DIGITS:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), expected)

    def test_latex_wrappers_are_unwrapped(self) -> None:
        for raw, expected in LATEX_WRAPPERS:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), expected)

    def test_symbols_and_relation_commands(self) -> None:
        for raw, expected in SYMBOLS_AND_RELATIONS:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), expected)

    def test_prose_around_math_is_preserved(self) -> None:
        for raw, expected in PROSE_AND_LAYOUT:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), expected)

    def test_escaped_dollar_does_not_break_span_pairing(self) -> None:
        for raw, expected in ESCAPED_DOLLAR:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), expected)

    def test_prose_whitespace_is_never_touched(self) -> None:
        # A mis-paired span would strip the space before the currency word.
        raw = r"for just under $\$ 2 8$ USD, which was cheap"
        self.assertEqual(normalize_text(raw), r"for just under $\$ 28$ USD, which was cheap")

    def test_text_without_math_is_returned_unchanged(self) -> None:
        for raw in NO_MATH_INPUTS:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), raw)

    def test_only_math_spans_are_rewritten(self) -> None:
        raw = r"Growth was $4 5 . 0 \%$ in 2024, up from $3 0 . 0 \%$ in 2023."
        expected = "Growth was $45.0%$ in 2024, up from $30.0%$ in 2023."
        self.assertEqual(normalize_text(raw), expected)

    def test_non_string_input_is_passed_through(self) -> None:
        for raw in (None, 17, ["$1 0$"]):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_text(raw), raw)


class NormalizeMathTest(unittest.TestCase):
    """Cover the fixed-point behaviour of the span rewriter."""

    def test_unbalanced_span_is_tolerated(self) -> None:
        self.assertEqual(normalize_math(r"1 0 ^ { 5 }"), "10^5")

    def test_empty_span_is_preserved(self) -> None:
        self.assertEqual(normalize_text("$ $"), "$ $")

    def test_result_is_idempotent(self) -> None:
        for raw, _ in ALL_CASES:
            with self.subTest(raw=raw):
                once = normalize_text(raw)
                self.assertEqual(normalize_text(once), once)

    def test_nested_spans_converge(self) -> None:
        self.assertEqual(normalize_text(r"$\{ 1 0 \} ^ { \mathrm { - 1 2 } }$"), "$10^-12$")

    def test_rule_hits_are_counted(self) -> None:
        stats: Counter[str] = Counter()
        normalize_text(r"$1 0 ^ { 5 }$", stats)
        self.assertGreater(stats["digit_glue_left"], 0)
        self.assertGreater(stats["brace_unwrap"], 0)

    def test_escaped_space_is_distinct_from_relation_command(self) -> None:
        # `\ =` goes through escaped_space, `\=` through relation_command.
        self.assertEqual(normalize_math(r"1 1 \ = \ 2 1"), "11 = 21")
        self.assertEqual(normalize_math(r"1 1 \= 2 1"), "11 = 21")


class BlankBlockTest(unittest.TestCase):
    """Cover detection of multimodal blocks MinerU emitted without payload."""

    def test_blank_table_is_detected(self) -> None:
        block = {
            "type": "table",
            "img_path": "",
            "table_caption": [],
            "table_footnote": [],
            "page_idx": 3,
        }
        self.assertTrue(is_blank_block(block))

    def test_whitespace_only_payload_still_counts_as_blank(self) -> None:
        block = {"type": "table", "img_path": "   ", "table_caption": [""]}
        self.assertTrue(is_blank_block(block))

    def test_table_with_body_is_kept(self) -> None:
        block = {"type": "table", "img_path": "", "table_body": "<table></table>"}
        self.assertFalse(is_blank_block(block))

    def test_table_with_caption_is_kept(self) -> None:
        block = {"type": "table", "img_path": "", "table_caption": ["Table 1."]}
        self.assertFalse(is_blank_block(block))

    def test_image_with_path_is_kept(self) -> None:
        block = {"type": "image", "img_path": "/tmp/a.jpg", "image_caption": []}
        self.assertFalse(is_blank_block(block))

    def test_image_with_only_caption_is_kept(self) -> None:
        # A caption alone is usable text, even without the rendered image.
        block = {"type": "image", "img_path": "", "image_caption": ["Fig. 7."]}
        self.assertFalse(is_blank_block(block))

    def test_text_and_equation_blocks_are_never_blank(self) -> None:
        for block in (
            {"type": "text", "text": ""},
            {"type": "equation", "text": ""},
            {"type": "text"},
        ):
            with self.subTest(block=block):
                self.assertFalse(is_blank_block(block))


class ResolveImagePathTest(unittest.TestCase):
    """Cover the rewrite that keeps image references working directory free."""

    def test_result_is_always_absolute(self) -> None:
        resolved = resolve_image_path("images/a.jpg", Path("some/relative/dir"))
        self.assertTrue(resolved.is_absolute())

    def test_mineru_relative_prefix_is_discarded(self) -> None:
        # The reference corpus uses this shape, which the upstream fixer misses
        # because it only rewrites references starting with `images/`.
        raw = "mineru-parsed/doc-1/auto/images/deadbeef.jpg"
        resolved = resolve_image_path(raw, Path("/corpus/doc-1/auto/images"))
        self.assertEqual(
            resolved, Path("/corpus/doc-1/auto/images/deadbeef.jpg").resolve()
        )

    def test_windows_separators_are_handled(self) -> None:
        resolved = resolve_image_path(r"images\sub\a.jpg", Path("/corpus/images"))
        self.assertEqual(resolved, Path("/corpus/images/a.jpg").resolve())

    def test_bare_filename_is_accepted(self) -> None:
        resolved = resolve_image_path("a.jpg", Path("/corpus/images"))
        self.assertEqual(resolved, Path("/corpus/images/a.jpg").resolve())


if __name__ == "__main__":
    unittest.main()
