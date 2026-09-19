"""Japanese display typesetting on top of Pillow.

Pillow draws a string with the font's default advances, which for Japanese
means every bracket, comma and full stop occupies a full em. In display sizes
that leaves visible holes - 「合う休み方」で、 reads as spaced out. OpenType
`palt` would fix it, but Zen Kaku Gothic New has no palt table, so the
compression is done here instead: punctuation is set on a half-em advance and
the glyph shifted so its ink lands where it should. This is 約物詰め.

The same advance model is used to measure and to draw, so a block that fits
when measured is exactly the block that gets drawn. Line breaking goes through
mbti_tiktok_bot.typeset, which owns kinsoku and particle-aware breaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PIL import ImageFont

from mbti_tiktok_bot.design.fonts import face
from mbti_tiktok_bot.typeset import break_points, wrap_text

# Ink in the right half of the em box: set at half width, shifted left.
OPENING = frozenset("「『（［｛〈《【〔“‘")
# Ink in the left half: set at half width where it stands.
CLOSING = frozenset("」』）］｝〉》】〕”’、。，．")
# Ink centred: set at half width, shifted left by a quarter.
MIDDLE = frozenset("・：；")

# Phrases the copy relies on reading as one unit. Mirrors the renderer's list.
PROTECTED_PHRASES = (
    "仲良くなるほど",
    "脈あり",
    "本命だけ",
    "距離の縮め方",
    "心を許した",
    "心を許す",
    "しんどい時",
    "LINE",
)


def _is_wide(char: str) -> bool:
    return ord(char) > 0x2E7F


@dataclass(frozen=True, slots=True)
class Glyph:
    char: str
    offset: float   # where to draw, relative to the pen position
    advance: float  # how far the pen moves afterwards


@lru_cache(maxsize=512)
def _font_by_key(font_key: tuple[str, int, int]) -> ImageFont.FreeTypeFont:
    path, index, size = font_key
    return ImageFont.truetype(path, size=size, index=index)


@lru_cache(maxsize=65536)
def _char_width(font_key: tuple[str, int, int], char: str) -> float:
    return _font_by_key(font_key).getlength(char)


def _font_key(font: ImageFont.FreeTypeFont) -> tuple[str, int, int]:
    return (font.path, font.index, font.size)


def glyphs(text: str, font: ImageFont.FreeTypeFont, tracking: float = 0.0, compress: bool = True) -> list[Glyph]:
    key = _font_key(font)
    result: list[Glyph] = []
    for position, char in enumerate(text):
        width = _char_width(key, char)
        offset = 0.0
        if compress and char in OPENING:
            offset, width = -width / 2, width / 2
        elif compress and char in CLOSING:
            width = width / 2
        elif compress and char in MIDDLE:
            offset, width = -width / 4, width / 2
        # Tracking goes between characters, never after the last one.
        gap = tracking if position < len(text) - 1 else 0.0
        result.append(Glyph(char, offset, width + gap))
    return result


def line_width(text: str, font: ImageFont.FreeTypeFont, tracking: float = 0.0, compress: bool = True) -> float:
    return sum(glyph.advance for glyph in glyphs(text, font, tracking, compress))


def _breaks_protected(original: str, wrapped: str) -> bool:
    if "\n" not in wrapped:
        return False
    flat_breaks: set[int] = set()
    position = 0
    for char in wrapped:
        if char == "\n":
            flat_breaks.add(position)
        else:
            position += 1
    for phrase in PROTECTED_PHRASES:
        start = original.find(phrase)
        while start != -1:
            if any(start < cut < start + len(phrase) for cut in flat_breaks):
                return True
            start = original.find(phrase, start + 1)
    return False


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in PROTECTED_PHRASES:
        start = text.find(phrase)
        while start != -1:
            spans.append((start, start + len(phrase)))
            start = text.find(phrase, start + 1)
    return spans


def headline_lines(
    text: str,
    font: ImageFont.FreeTypeFont,
    tracking: float,
    max_width: float,
    max_lines: int,
    compress: bool = True,
) -> list[str] | None:
    """Split a headline only where a reader would, into as few even lines as fit.

    The general wrapper fills lines and treats を as a fine place to break, so
    心を許したサイン came out as 心を / 許したサイン at every size. Headlines are
    short enough to search properly: candidate breaks are the preferred and
    fallback points outside any protected phrase, and among the partitions with
    the fewest lines that fit, the one with the most even line lengths wins.
    Returns None when no partition fits.
    """
    if not text:
        return [""]
    if line_width(text, font, tracking, compress) <= max_width:
        return [text]
    preferred, fallback = break_points(text)
    spans = _protected_spans(text)
    cuts = sorted(
        position for position in preferred | fallback
        if 0 < position < len(text) and not any(start < position < end for start, end in spans)
    )
    points = [0, *cuts, len(text)]
    widths: dict[tuple[int, int], float] = {}

    def width(a: int, b: int) -> float:
        key = (a, b)
        if key not in widths:
            widths[key] = line_width(text[a:b], font, tracking, compress)
        return widths[key]

    total = line_width(text, font, tracking, compress)
    for count in range(2, max_lines + 1):
        target = total / count
        # best[(line_index, point)] = (cost, previous point)
        best: dict[tuple[int, int], tuple[float, int]] = {(0, 0): (0.0, -1)}
        for line in range(1, count + 1):
            for end in points[1:]:
                if line == count and end != len(text):
                    continue
                for start in points:
                    if start >= end or (line - 1, start) not in best:
                        continue
                    span = width(start, end)
                    if span > max_width:
                        continue
                    cost = best[(line - 1, start)][0] + (span - target) ** 2
                    if (line, end) not in best or cost < best[(line, end)][0]:
                        best[(line, end)] = (cost, start)
        if (count, len(text)) in best:
            lines: list[str] = []
            line, end = count, len(text)
            while line > 0:
                start = best[(line, end)][1]
                lines.append(text[start:end])
                line, end = line - 1, start
            return list(reversed(lines))
    return None


def _bad_breaks(text: str, lines: list[str], strict: bool) -> int:
    """Count line breaks a reader would stumble on.

    A break inside a word (時/間, 休/み方) always counts in strict mode, which
    headlines use. A last line of one or two characters counts everywhere: 余白
    set as 余 / 白 leaves a single glyph stranded under a wall of type.
    """
    bad = 0
    if len(lines) > 1 and len(lines[-1]) <= 2 and len(text) > 6:
        bad += 1
    if strict and len(lines) > 1:
        flat = "".join(lines)
        preferred, fallback = break_points(flat)
        allowed = preferred | fallback
        position = 0
        for line in lines[:-1]:
            position += len(line)
            if position not in allowed:
                bad += 1
    return bad


@dataclass(frozen=True, slots=True)
class Block:
    """A typeset paragraph, measured in logical pixels."""

    lines: tuple[str, ...]
    role: str
    size: int
    tracking: float
    leading: float  # line pitch as a multiple of size
    width: float
    height: float
    compress: bool = True

    @property
    def font(self) -> ImageFont.FreeTypeFont:
        return face(self.role, self.size)

    @property
    def pitch(self) -> float:
        return self.size * self.leading


def _block(lines: list[str], role: str, size: int, tracking_em: float, leading: float, compress: bool) -> Block:
    font = face(role, size)
    tracking = tracking_em * size
    width = max((line_width(line, font, tracking, compress) for line in lines), default=0.0)
    height = (len(lines) - 1) * size * leading + size if lines else 0.0
    return Block(tuple(lines), role, size, tracking, leading, width, height, compress)


def fit(
    text: str,
    role: str,
    max_width: float,
    max_height: float,
    base: int,
    minimum: int,
    *,
    leading: float = 1.25,
    tracking_em: float = 0.0,
    max_lines: int | None = None,
    step: int = 2,
    compress: bool = True,
    strict: bool = False,
) -> Block:
    """The largest setting of text that fits the box, stepping down from base.

    strict (for headlines) also refuses breaks inside a word, so a title with
    no good break point is shrunk onto one line rather than cut mid-word. A
    stranded one- or two-character last line is refused in either mode.
    Anything imperfect is accepted only when no size in range avoids it.
    """
    best: tuple[tuple[float, int, int], Block] | None = None
    for size in range(base, minimum - 1, -step):
        font = face(role, size)
        tracking = tracking_em * size
        planned = (
            headline_lines(text, font, tracking, max_width, max_lines or 4, compress)
            if strict and "\n" not in text
            else None
        )
        if planned is not None:
            lines = planned
            wrapped = "\n".join(lines)
        else:
            wrapped = wrap_text(lambda value: line_width(value, font, tracking, compress), text, int(max_width))
            lines = [line for line in wrapped.split("\n")]
        block = _block(lines, role, size, tracking_em, leading, compress)
        too_many = max_lines is not None and len(lines) > max_lines
        overflow = max(block.width - max_width, 0) + max(block.height - max_height, 0) + (10_000 if too_many else 0)
        bad = _bad_breaks(text, lines, strict)
        broken = 1 if _breaks_protected(text, wrapped) else 0
        if overflow == 0 and not bad and not broken:
            return block
        rank = (overflow, bad, broken)
        if best is None or rank < best[0]:
            best = (rank, block)
    assert best is not None
    return best[1]


def single(text: str, role: str, size: int, *, tracking_em: float = 0.0, compress: bool = True) -> Block:
    """One unwrapped line at a fixed size, for labels and numbers."""
    return _block([text], role, size, tracking_em, 1.0, compress)


def fit_single(text: str, role: str, max_width: float, base: int, minimum: int, *, tracking_em: float = 0.0) -> Block:
    """One line, shrunk until it fits the width."""
    for size in range(base, minimum - 1, -1):
        block = single(text, role, size, tracking_em=tracking_em)
        if block.width <= max_width:
            return block
    return single(text, role, minimum, tracking_em=tracking_em)


@lru_cache(maxsize=512)
def _ink_top(font_key: tuple[str, int, int], sample: str) -> float:
    """Distance from the baseline up to the top of the ink, for optical alignment."""
    return -_font_by_key(font_key).getbbox(sample, anchor="ls")[1]


def _reference_glyph(text: str) -> str:
    return "国" if any(_is_wide(char) for char in text) else "H"


def ink_height(block: Block) -> float:
    """Height of one line's ink, for centring text optically inside a shape."""
    reference = _reference_glyph("".join(block.lines))
    top, bottom = _font_by_key(_font_key(block.font)).getbbox(reference, anchor="ls")[1::2]
    return bottom - top


def draw(
    canvas,
    block: Block,
    x: float,
    y: float,
    fill,
    *,
    align: str = "left",
    box_width: float | None = None,
    stroke: int = 0,
    stroke_fill=None,
    shadow: tuple[float, float, tuple[int, int, int, int]] | None = None,
) -> None:
    """Draw a block with its ink top at y.

    Stroked text is drawn in two passes - every outline, then every fill - so
    neighbouring glyphs' outlines join instead of cutting into each other.
    """
    font = block.font
    reference = _reference_glyph("".join(block.lines))
    ascent = _ink_top(_font_key(font), reference)
    width = box_width if box_width is not None else block.width

    placements: list[tuple[float, float, str]] = []
    for row, line in enumerate(block.lines):
        line_advance = line_width(line, font, block.tracking, block.compress)
        if align == "center":
            start = x + (width - line_advance) / 2
        elif align == "right":
            start = x + width - line_advance
        else:
            start = x
        baseline = y + row * block.pitch + ascent
        pen = start
        for glyph in glyphs(line, font, block.tracking, block.compress):
            placements.append((pen + glyph.offset, baseline, glyph.char))
            pen += glyph.advance

    if shadow is not None:
        dx, dy, color = shadow
        for px, py, char in placements:
            canvas.text((px + dx, py + dy), char, fill=color, font=font, anchor="ls",
                        stroke_width=stroke, stroke_fill=color)
    if stroke:
        for px, py, char in placements:
            canvas.text((px, py), char, fill=stroke_fill, font=font, anchor="ls",
                        stroke_width=stroke, stroke_fill=stroke_fill)
    for px, py, char in placements:
        canvas.text((px, py), char, fill=fill, font=font, anchor="ls")
