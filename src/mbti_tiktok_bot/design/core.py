"""The pieces every style shares: what a slide is, and how chips are laid out.

Coordinates are logical 1080x1920 throughout; ScaledDraw turns them into
render-scale pixels.
"""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field

from PIL import Image

from mbti_tiktok_bot.catalog import Palette
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.effects import hex_rgb
from mbti_tiktok_bot.models import ContentPackage

WIDTH = 1080
HEIGHT = 1920
# TikTok lays its own interface over a photo post: the tabs across the top, the
# action rail down the right edge, the caption across the bottom. Copy that has
# to be read stays inside this box; art and decoration may run under the rest.
SAFE_LEFT = 72
SAFE_TOP = 172
SAFE_RIGHT = 936
SAFE_BOTTOM = 1540
SAFE_WIDTH = SAFE_RIGHT - SAFE_LEFT


@dataclass(frozen=True, slots=True)
class Slide:
    kind: str  # "cover", "body" or "closer"
    index: int  # position in the carousel, from 0
    number: int  # 1-based position among the body slides; 0 on cover and closer
    total: int  # how many body slides the carousel has
    title: str
    body: str
    chips: tuple[str, ...] = ()


@dataclass(slots=True)
class Context:
    package: ContentPackage
    config: AppConfig
    palette: Palette
    topic_seed: int
    subject: Image.Image  # the character cutout, trimmed to its alpha
    scale: int
    cache: dict = field(default_factory=dict)

    @property
    def device(self) -> tuple[int, int]:
        return (WIDTH * self.scale, HEIGHT * self.scale)

    def px(self, value: float) -> int:
        return round(value * self.scale)

    def box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return tuple(self.px(value) for value in box)  # type: ignore[return-value]


# The trait lists in the copy used to be joined with " / " and dropped into
# prose, which put 場を明るくする / 愛嬌がある / ... on the slide verbatim. A
# leading run like that becomes chips; one in the middle of a sentence is
# re-joined with a middle dot so it reads as Japanese.
# A trait is a short phrase with no comma or space in it; a sentence that
# merely contains a list later on must not be mistaken for one.
_TRAIT = r"[^。/、\s]{1,20}"
_LEADING_LIST = re.compile(rf"^((?:{_TRAIT} / )+{_TRAIT})。")


# Templates write f"実際は {traits} が出ている", which leaves ASCII spaces between
# Japanese words. Japanese is set without them; Latin words keep theirs.
_SPACE_BETWEEN_WIDE = re.compile(r"(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])")


def split_chips(body: str) -> tuple[tuple[str, ...], str]:
    match = _LEADING_LIST.match(body)
    if match:
        chips = tuple(part.strip() for part in match.group(1).split(" / ") if part.strip())
        body = body[match.end():].strip()
    else:
        chips = ()
    body = body.replace(" / ", "・")
    return chips, _SPACE_BETWEEN_WIDE.sub("", body)


def slides_for(package: ContentPackage) -> list[Slide]:
    """Turn the render package's scenes into cover, body and closer slides."""
    scenes = package.scenes
    total = max(len(scenes) - 2, 0)
    result: list[Slide] = []
    for index, scene in enumerate(scenes):
        if index == 0:
            kind, number = "cover", 0
        elif index == len(scenes) - 1:
            kind, number = "closer", 0
        else:
            kind, number = "body", index
        chips, body = split_chips(scene.body)
        result.append(Slide(kind, index, number, total, scene.title, body, chips))
    return result


def hue_shift(color: str, degrees: float, saturation: float = 1.0, value: float = 1.0) -> str:
    r, g, b = (channel / 255 for channel in hex_rgb(color))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + degrees / 360) % 1.0
    s = min(max(s * saturation, 0.0), 1.0)
    v = min(max(v * value, 0.0), 1.0)
    return "#%02x%02x%02x" % tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(h, s, v))


def hue_of(color: str) -> float:
    r, g, b = (channel / 255 for channel in hex_rgb(color))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def vivid(color: str, saturation: float = 0.9, value: float = 1.0) -> str:
    """The same hue pushed to a given saturation and brightness."""
    h = hue_of(color) / 360
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, saturation, value))


def neon_partner(color: str) -> str:
    """A second glow that sits well next to color.

    A fixed hue rotation pairs orange with green, which reads as mud. These are
    the pairings neon work actually uses: warm with pink, green with magenta,
    blue with violet, purple with cyan.
    """
    hue = hue_of(color)
    if hue < 70 or hue >= 330:
        target = 328
    elif hue < 170:
        target = 300
    elif hue < 250:
        target = 272
    else:
        target = 190
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in colorsys.hsv_to_rgb(target / 360, 0.78, 1.0))


def luminance(color: str) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = hex_rgb(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


# --- chips -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Chip:
    """A label that is exactly as wide as its text.

    The old renderer drew a fixed box and centred the text in it, so a long
    label - エンターテイナー is the only eight-character archetype - hung out
    of both ends and onto its neighbour.
    """

    label: str
    role: str
    size: int
    fill: tuple[int, int, int, int] | None
    color: tuple[int, int, int, int]
    outline: tuple[int, int, int, int] | None = None
    tracking_em: float = 0.04
    pad_x: float = 0.9  # horizontal padding, in multiples of size
    height_em: float = 2.0
    stroke: int = 2

    @property
    def block(self) -> T.Block:
        return T.single(self.label, self.role, self.size, tracking_em=self.tracking_em)

    @property
    def height(self) -> float:
        return self.size * self.height_em

    @property
    def width(self) -> float:
        return self.block.width + self.size * self.pad_x * 2

    def resized(self, size: int) -> "Chip":
        return Chip(self.label, self.role, size, self.fill, self.color, self.outline,
                    self.tracking_em, self.pad_x, self.height_em, self.stroke)


def draw_chip(canvas, chip: Chip, x: float, y: float) -> float:
    """Draw one chip with its top-left at (x, y). Returns its width."""
    width, height = chip.width, chip.height
    radius = height / 2
    if chip.fill is not None or chip.outline is not None:
        canvas.rounded_rectangle(
            (x, y, x + width, y + height),
            radius=radius,
            fill=chip.fill,
            outline=chip.outline,
            width=chip.stroke if chip.outline else 1,
        )
    block = chip.block
    # Centre the ink, not the em box: textbbox origins put the glyphs low.
    text_y = y + (height - T.ink_height(block)) / 2
    T.draw(canvas, block, x + chip.size * chip.pad_x, text_y, chip.color)
    return width


def chip_row(canvas, chips: list[Chip], x: float, y: float, max_width: float, gap: float = 14,
             align: str = "left", draw: bool = True) -> tuple[float, float]:
    """Lay chips left to right from one origin, dropping those that do not fit.

    A single chip that is too wide on its own is shrunk rather than dropped.
    Returns the (width, height) actually used.
    """
    placed: list[Chip] = []
    used = 0.0
    for chip in chips:
        candidate = chip
        if not placed:
            size = chip.size
            while candidate.width > max_width and size > 14:
                size -= 1
                candidate = chip.resized(size)
        extra = candidate.width + (gap if placed else 0)
        if used + extra > max_width:
            break
        placed.append(candidate)
        used += extra
    if not placed:
        return (0.0, 0.0)
    height = max(chip.height for chip in placed)
    if draw:
        start = x + (max_width - used) if align == "right" else (x + (max_width - used) / 2 if align == "center" else x)
        pen = start
        for chip in placed:
            pen += draw_chip(canvas, chip, pen, y + (height - chip.height) / 2) + gap
    return (used, height)


def chip_flow(canvas, chips: list[Chip], x: float, y: float, max_width: float, gap: float = 14,
              line_gap: float = 14, max_rows: int = 3, draw: bool = True) -> float:
    """Wrap chips onto as many rows as needed. Returns the height used."""
    rows: list[list[Chip]] = [[]]
    used = 0.0
    for chip in chips:
        width = min(chip.width, max_width)
        extra = width + (gap if rows[-1] else 0)
        if rows[-1] and used + extra > max_width:
            if len(rows) == max_rows:
                break
            rows.append([])
            used, extra = 0.0, width
        rows[-1].append(chip)
        used += extra
    top = y
    for row in rows:
        if not row:
            continue
        _, height = chip_row(canvas, row, x, top, max_width, gap, draw=draw)
        top += height + line_gap
    return top - y - line_gap if top > y else 0.0
