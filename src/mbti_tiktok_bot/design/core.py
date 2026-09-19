"""What every look and layout shares: the canvas, the context, chips.

Coordinates are logical 1080x1920 throughout; ScaledDraw turns them into
render-scale pixels.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image

from mbti_tiktok_bot.catalog import Palette
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.effects import hex_rgb, trim

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


@lru_cache(maxsize=32)
def _load_cutout(path: str) -> Image.Image:
    with Image.open(path) as opened:
        return trim(opened.convert("RGBA"))


@dataclass(slots=True)
class Context:
    config: AppConfig
    palette: Palette
    seed: int
    scale: int
    cache: dict = field(default_factory=dict)

    @property
    def device(self) -> tuple[int, int]:
        return (WIDTH * self.scale, HEIGHT * self.scale)

    def px(self, value: float) -> int:
        return round(value * self.scale)

    def box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return tuple(self.px(value) for value in box)  # type: ignore[return-value]

    def subject_of(self, mbti: str) -> Image.Image:
        """The provided illustration for a type, trimmed to its alpha."""
        from mbti_tiktok_bot.visuals import _resolve_illustration_path

        source = _resolve_illustration_path(self.config, mbti)
        if source is None:
            # Substituting a generated figure for a missing type is exactly what
            # the provided-material policy rules out.
            raise FileNotFoundError(
                f"Provided MBTI material is required for {mbti}; "
                f"place it in {self.config.official_images_dir} or {self.config.assets_dir}"
            )
        return _load_cutout(str(source))


# --- colour -----------------------------------------------------------------


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


# --- chips ------------------------------------------------------------------


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
    pad_x: float = 0.9
    height_em: float = 2.0
    stroke: int = 2
    square: bool = False

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
                    self.tracking_em, self.pad_x, self.height_em, self.stroke, self.square)


def draw_chip(canvas, chip: Chip, x: float, y: float) -> float:
    """Draw one chip with its top-left at (x, y). Returns its width."""
    width, height = chip.width, chip.height
    if chip.fill is not None or chip.outline is not None:
        box = (x, y, x + width, y + height)
        if chip.square:
            canvas.rectangle(box, fill=chip.fill, outline=chip.outline, width=chip.stroke if chip.outline else 1)
        else:
            canvas.rounded_rectangle(box, radius=height / 2, fill=chip.fill, outline=chip.outline,
                                     width=chip.stroke if chip.outline else 1)
    block = chip.block
    # Centre the ink, not the em box: textbbox origins put the glyphs low.
    T.draw(canvas, block, x + chip.size * chip.pad_x, y + (height - T.ink_height(block)) / 2, chip.color)
    return width


def chip_row(canvas, chips: list[Chip], x: float, y: float, max_width: float, gap: float = 14,
             align: str = "left", draw: bool = True) -> tuple[float, float]:
    """Lay chips left to right from one origin, dropping those that do not fit.

    A single chip too wide on its own is shrunk rather than dropped.
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
        if align == "right":
            pen = x + max_width - used
        elif align == "center":
            pen = x + (max_width - used) / 2
        else:
            pen = x
        for chip in placed:
            pen += draw_chip(canvas, chip, pen, y + (height - chip.height) / 2) + gap
    return (used, height)


def chip_flow(canvas, chips: list[Chip], x: float, y: float, max_width: float, gap: float = 14,
              line_gap: float = 14, max_rows: int = 3, draw: bool = True, align: str = "left") -> float:
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
        _, height = chip_row(canvas, row, x, top, max_width, gap, align=align, draw=draw)
        top += height + line_gap
    return top - y - line_gap if top > y else 0.0
