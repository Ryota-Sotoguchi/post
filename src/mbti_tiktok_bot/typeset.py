"""Japanese line breaking for the slide renderer.

The previous wrapper filled each line to the pixel limit and then tried to
repair the result, which split words like 急かさない across lines and stranded
particles at the start of the next one. This breaks at bunsetsu-ish boundaries
instead, and aims for lines of even length rather than lines packed to the
margin, because a slide reads as one block rather than a paragraph.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Callable

# Characters that may not open a line (行頭禁則).
LINE_START_FORBIDDEN = frozenset(
    "、。，．・：；！？」』）］｝〉》〕】ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮーヽヾ゛゜々〜"
    ",.:;!?)]}’”"
)
# Characters that may not close a line (行末禁則).
LINE_END_FORBIDDEN = frozenset("「『（［｛〈《〔【([{‘“")

# Longest first: breaking after the の of のに would be wrong.
MULTI_CHAR_PARTICLES = (
    "について", "における", "けれど", "なので", "だから",
    "から", "まで", "より", "ので", "のに", "ため", "けど", "でも", "とか", "など",
)
# も, や, ね, よ and か are left out on purpose: they turn up inside いつも,
# 冷やす, 重ねる, しよう and 急かす far more often than they end a bunsetsu.
SINGLE_CHAR_PARTICLES = ("を", "に", "は", "が", "の", "へ", "と", "で")
BREAK_AFTER_PARTICLES = MULTI_CHAR_PARTICLES + SINGLE_CHAR_PARTICLES
SENTENCE_ENDS = frozenset("。．！？!?、，,")
COMPOUND_PARTICLE_TAILS = frozenset("はがをにへとでもの")

Measure = Callable[[str], int]


def _is_latin_or_digit(char: str) -> bool:
    return char.isascii() and char.isalnum()


def _is_katakana(char: str) -> bool:
    return "KATAKANA" in unicodedata.name(char, "")


def _is_content_char(char: str) -> bool:
    """Kanji, katakana, latin, digits and closing marks end a word.

    A single-char particle only reads as a particle after one of these. After
    hiragana it is usually okurigana, as in 急かす or いつも.
    """
    if _is_latin_or_digit(char) or _is_katakana(char):
        return True
    if char in "」』）］｝〉》〕】)]}’”":
        return True
    return "CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "")


def _joins_with_next(previous: str, following: str) -> bool:
    """True when a break between these two characters would split a token."""
    if _is_latin_or_digit(previous) and _is_latin_or_digit(following):
        return True
    if _is_katakana(previous) and _is_katakana(following):
        return True
    return False


def break_points(text: str) -> tuple[set[int], set[int]]:
    """Indices where a new line may start, split into preferred and fallback.

    Preferred breaks follow punctuation, a multi-character particle or a
    particle attached to a content word. Fallback breaks follow a particle
    written after hiragana, which is ambiguous (the が of ことが is a particle,
    the か of 急かす is not) but still reads better than cutting mid-word.
    """
    preferred: set[int] = set()
    fallback: set[int] = set()
    length = len(text)

    for index in range(1, length):
        previous = text[index - 1]
        following = text[index]
        if following in LINE_START_FORBIDDEN or previous in LINE_END_FORBIDDEN:
            continue
        if previous in SENTENCE_ENDS:
            preferred.add(index)
            continue
        if _joins_with_next(previous, following):
            continue
        if following in LINE_END_FORBIDDEN:
            # An opening bracket wants to start the line it belongs to.
            preferred.add(index)
            continue
        # A particle glued to another one is a compound (への, とは, からも),
        # so only break where the run of particles actually ends.
        if following in COMPOUND_PARTICLE_TAILS:
            continue

        for particle in BREAK_AFTER_PARTICLES:
            start = index - len(particle)
            if start <= 0 or text[start:index] != particle:
                continue
            # Skip when this is only the head of a longer particle running past
            # index, so より is not read as よ followed by り.
            if any(
                other != particle
                and other.startswith(particle)
                and text[start : start + len(other)] == other
                for other in BREAK_AFTER_PARTICLES
            ):
                break
            if particle in SINGLE_CHAR_PARTICLES and not _is_content_char(text[start - 1]):
                fallback.add(index)
                break
            preferred.add(index)
            break

    return preferred, fallback


def _max_fit(measure: Measure, text: str, start: int, limit: int) -> int:
    """Largest end index whose slice still fits within limit."""
    end = start
    for index in range(start + 1, len(text) + 1):
        if measure(text[start:index]) > limit:
            break
        end = index
    return end


def _kinsoku_adjust(text: str, start: int, cut: int) -> int:
    while cut > start + 1 and cut < len(text) and text[cut] in LINE_START_FORBIDDEN:
        cut -= 1
    while cut > start + 1 and text[cut - 1] in LINE_END_FORBIDDEN:
        cut -= 1
    return cut


def _fill(measure: Measure, text: str, max_width: int, target_width: float) -> list[str]:
    preferred_points, fallback_points = break_points(text)
    lines: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        if measure(text[start:]) <= max_width:
            lines.append(text[start:])
            break

        hard_end = max(_max_fit(measure, text, start, max_width), start + 1)

        def nearest(points: set[int]) -> int | None:
            # Closest to the target line length, not the longest that fits, so
            # the block ends up even instead of full lines plus one orphan.
            candidates = [point for point in points if start < point <= hard_end]
            if not candidates:
                return None
            return min(candidates, key=lambda point: abs(measure(text[start:point]) - target_width))

        cut = nearest(preferred_points)
        if cut is None:
            cut = nearest(fallback_points)
        if cut is None:
            cut = _kinsoku_adjust(text, start, hard_end)

        lines.append(text[start:cut])
        start = cut

    return [line for line in lines if line]


def wrap_paragraph(measure: Measure, text: str, max_width: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return [""]

    total = measure(stripped)
    if total <= max_width:
        return [stripped]

    # Spread the copy over as few lines as it needs, then even them out so the
    # block reads as a shape rather than a full line followed by one orphan.
    minimum_lines = max(2, math.ceil(total / max_width))
    for line_count in range(minimum_lines, minimum_lines + 4):
        lines = _fill(measure, stripped, max_width, total / line_count)
        if lines and all(measure(line) <= max_width for line in lines):
            return lines

    return _fill(measure, stripped, max_width, max_width)


def wrap_text(measure: Measure, text: str, max_width: int) -> str:
    wrapped: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            wrapped.append("")
            continue
        wrapped.extend(wrap_paragraph(measure, paragraph, max_width))
    return "\n".join(wrapped)
