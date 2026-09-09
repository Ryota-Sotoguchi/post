from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from mbti_tiktok_bot.catalog import GROUP_PALETTE_VARIANTS, GROUP_PALETTES, Palette
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.fonts import load_font
from mbti_tiktok_bot.models import CLOSER_SCENE_BODY, CLOSER_SCENE_TITLE, ContentPackage, Scene, SceneRenderAssets
from mbti_tiktok_bot.typeset import wrap_text


@dataclass(frozen=True, slots=True)
class LayoutProfile:
    title_panel: tuple[int, int, int, int]
    title_label_left: tuple[int, int, int, int]
    title_label_right: tuple[int, int, int, int]
    title_content_region: tuple[int, int, int, int]
    title_hook_inset: tuple[int, int]
    thumbnail_card: tuple[int, int, int, int]
    thumbnail_label_left: tuple[int, int, int, int]
    thumbnail_label_right: tuple[int, int, int, int]
    thumbnail_content_region: tuple[int, int, int, int]
    character_box: tuple[int, int, int, int]
    density_axis: str
    density_shift: int


PULSE_CHARACTER_BOX = (784, 150, 1044, 680)
PULSE_MAIN_CARD = (72, 760, 1008, 1648)
PULSE_THUMBNAIL_CARD = (72, 820, 1008, 1648)
PULSE_CLOSER_CARD = (72, 720, 1008, 1680)
# Hard floor for shrink-to-fit; below this Japanese copy stops being legible
# on a 1080x1920 canvas, so overflowing is the lesser evil.
ABSOLUTE_MIN_FONT_SIZE = 14
PROTECTED_JAPANESE_PHRASES = (
    "仲良くなるほど",
    "好きな人",
    "脈あり",
    "本命だけ",
    "本気で",
    "心を許した",
    "距離の縮め方",
    "急に変わる瞬間",
    "素の反応",
    "最初の1秒",
    "要チェック",
    "盛り上がり",
    "返信速度",
    "返信の温度差",
    "本気サイン",
    "分かる",
    "見せる",
    "変わる",
    "縮める",
    "出る",
)


# Pillow's ImageDraw does not antialias polygons, arcs, outlines or rounded
# corners, so everything drawn here lands with stair-stepped edges. Rendering
# at RENDER_SCALE and downsampling once with LANCZOS at compose time fixes that
# without touching the several hundred coordinate literals in this module:
# ScaledDraw takes logical 1080x1920 coordinates and scales them on the way
# through. Set to 1 to render exactly as before.
RENDER_SCALE = 2


def _scale_xy(xy, scale: int):
    """Scale an ImageDraw coordinate argument in any shape this module uses.

    Handles a flat 2- or 4-tuple, and a list or tuple of points.
    """
    if scale == 1:
        return xy
    if isinstance(xy[0], (list, tuple)):
        return [tuple(round(value * scale) for value in point) for point in xy]
    return tuple(round(value * scale) for value in xy)


@lru_cache(maxsize=512)
def _device_font(path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


@lru_cache(maxsize=1)
def _measure_draw() -> ImageDraw.ImageDraw:
    """One scratch 1x context for every text measurement in this module.

    Measuring has to stay at logical scale. The shrink-to-fit ladder in
    _fit_wrapped_text steps by 2, so measuring at 2x lets it settle on sizes
    the 1x ladder cannot reach, and the chosen font size and line breaks drift.
    """
    return ImageDraw.Draw(Image.new("L", (1, 1)))


class ScaledDraw:
    """Draws in logical 1080x1920 coordinates onto a scale-times-larger canvas.

    Only the methods this module actually draws with are forwarded. Anything
    else raises: a call that slipped through unscaled would draw at 1x into a
    2x canvas and produce a slide that looks almost right. Measurement is
    deliberately absent - use _measure_draw().
    """

    __slots__ = ("image", "scale", "_draw")

    def __init__(self, image: Image.Image, scale: int = RENDER_SCALE) -> None:
        self.image = image
        self.scale = scale
        self._draw = ImageDraw.Draw(image)

    def __getattr__(self, name: str):
        raise AttributeError(
            f"ScaledDraw does not forward {name!r}. Add an explicit wrapper so its "
            "coordinates are scaled, or measure through _measure_draw()."
        )

    # -- sibling layers and units --------------------------------------------
    def layer(self, fill: tuple[int, int, int, int] = (0, 0, 0, 0)) -> Image.Image:
        return Image.new("RGBA", self.image.size, fill)

    def sub(self, image: Image.Image) -> "ScaledDraw":
        return ScaledDraw(image, self.scale)

    def blur(self, radius: float) -> ImageFilter.Filter:
        return ImageFilter.GaussianBlur(radius * self.scale)

    def px(self, value: float) -> int:
        """Logical to device, for paste/alpha_composite offsets and sizes."""
        return round(value * self.scale)

    def _w(self, width: int) -> int:
        return max(1, round(width * self.scale)) if width else width

    def _font(self, font):
        if font is None or self.scale == 1:
            return font
        return _device_font(font.path, font.index, round(font.size * self.scale))

    # -- geometry -------------------------------------------------------------
    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, **kwargs):
        self._draw.rounded_rectangle(
            _scale_xy(xy, self.scale), radius=radius * self.scale,
            fill=fill, outline=outline, width=self._w(width), **kwargs)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        self._draw.rectangle(_scale_xy(xy, self.scale), fill=fill, outline=outline, width=self._w(width))

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self._draw.ellipse(_scale_xy(xy, self.scale), fill=fill, outline=outline, width=self._w(width))

    def polygon(self, xy, fill=None, outline=None, width=1):
        self._draw.polygon(_scale_xy(xy, self.scale), fill=fill, outline=outline, width=self._w(width))

    def line(self, xy, fill=None, width=0, joint=None):
        self._draw.line(_scale_xy(xy, self.scale), fill=fill, width=self._w(width), joint=joint)

    # start and end are angles in degrees. Scaling them would rotate the shape.
    def arc(self, xy, start, end, fill=None, width=1):
        self._draw.arc(_scale_xy(xy, self.scale), start, end, fill=fill, width=self._w(width))

    def pieslice(self, xy, start, end, fill=None, outline=None, width=1):
        self._draw.pieslice(_scale_xy(xy, self.scale), start, end, fill=fill, outline=outline, width=self._w(width))

    # -- text -----------------------------------------------------------------
    def text(self, xy, text, fill=None, font=None, anchor=None, spacing=4, align="left",
             stroke_width=0, stroke_fill=None):
        self._draw.text(
            _scale_xy(xy, self.scale), text, fill=fill, font=self._font(font), anchor=anchor,
            spacing=spacing * self.scale, align=align,
            stroke_width=round(stroke_width * self.scale), stroke_fill=stroke_fill)

    def multiline_text(self, xy, text, fill=None, font=None, anchor=None, spacing=4, align="left",
                       stroke_width=0, stroke_fill=None):
        self._draw.multiline_text(
            _scale_xy(xy, self.scale), text, fill=fill, font=self._font(font), anchor=anchor,
            spacing=spacing * self.scale, align=align,
            stroke_width=round(stroke_width * self.scale), stroke_fill=stroke_fill)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return load_font(size, bold=bold)


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return (
        int(hex_color[1:3], 16),
        int(hex_color[3:5], 16),
        int(hex_color[5:7], 16),
        alpha,
    )


# Eight bits over 1920 rows is not enough for a slow gradient: adjacent rows
# round to the same value for up to eighteen rows at a time, and the flat bands
# are visible. A little luminance noise breaks them up, and the downsample
# averages it back towards invisible.
GRADIENT_DITHER_SIGMA = 4


def _make_gradient(width: int, height: int, start_hex: str, end_hex: str) -> Image.Image:
    start = tuple(int(start_hex[i : i + 2], 16) for i in (1, 3, 5))
    end = tuple(int(end_hex[i : i + 2], 16) for i in (1, 3, 5))
    # One exact column stretched across, rather than a draw.line per row.
    span = max(height - 1, 1)
    strip = Image.new("RGB", (1, height))
    strip.putdata([
        tuple(int(start[channel] + (end[channel] - start[channel]) * y / span) for channel in range(3))
        for y in range(height)
    ])
    image = strip.resize((width, height), Image.Resampling.NEAREST)

    if GRADIENT_DITHER_SIGMA:
        noise = Image.effect_noise((width, height), GRADIENT_DITHER_SIGMA)
        # One channel for all three, so this dithers luminance without
        # speckling the hue.
        image = ImageChops.add(image, Image.merge("RGB", (noise, noise, noise)), scale=1, offset=-128)
    return image.convert("RGBA")


def _wrap_text(draw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    scratch = _measure_draw()

    def measure(value: str) -> int:
        return scratch.textbbox((0, 0), value, font=font)[2]

    return wrap_text(measure, text, max_width)


def _breaks_protected_japanese_phrase(original: str, wrapped: str) -> bool:
    plain_index = 0
    break_positions: set[int] = set()
    for char in wrapped:
        if char == "\n":
            break_positions.add(plain_index)
        elif not char.isspace():
            plain_index += 1

    plain_original = "".join(char for char in original if not char.isspace())
    for phrase in PROTECTED_JAPANESE_PHRASES:
        start = 0
        while True:
            found = plain_original.find(phrase, start)
            if found < 0:
                break
            phrase_breaks = range(found + 1, found + len(phrase))
            if any(position in break_positions for position in phrase_breaks):
                return True
            start = found + len(phrase)
    return False


def _fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    base_size: int,
    *,
    bold: bool = False,
    spacing: int = 8,
    min_size: int = 24,
    min_spacing: int = 4,
) -> tuple[str, ImageFont.ImageFont, int]:
    resolved_min_size = min(base_size, min_size)
    resolved_min_spacing = min(spacing, min_spacing)
    spacing_candidates = list(range(spacing, resolved_min_spacing - 1, -2)) or [resolved_min_spacing]

    size_candidates = list(range(base_size, resolved_min_size - 1, -2))
    # A box too small for the copy used to fall through to a blind minimum-size
    # render that spilled outside its panel, so keep shrinking past the caller's
    # preferred minimum before giving up. Font metrics differ per platform, and
    # a one-pixel overflow on one machine is still an overflow.
    size_candidates += list(range(resolved_min_size - 1, ABSOLUTE_MIN_FONT_SIZE - 1, -1))

    best_effort: tuple[tuple[int, int], str, ImageFont.FreeTypeFont, int] | None = None

    for font_size in size_candidates:
        font = _load_font(font_size, bold=bold)
        wrapped = _wrap_text(draw, text, font, max_width)
        breaks_phrase = _breaks_protected_japanese_phrase(text, wrapped)
        for line_spacing in spacing_candidates:
            text_box = _measure_draw().multiline_textbbox((0, 0), wrapped, font=font, spacing=line_spacing)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            overflow = max(text_width - max_width, 0) + max(text_height - max_height, 0)
            if overflow == 0 and not breaks_phrase:
                return wrapped, font, line_spacing
            # Rank fitting-but-phrase-breaking above anything that overflows.
            rank = (overflow, 1 if breaks_phrase else 0)
            if best_effort is None or rank < best_effort[0]:
                best_effort = (rank, wrapped, font, line_spacing)

    if best_effort is not None:
        _, wrapped, font, line_spacing = best_effort
        return wrapped, font, line_spacing

    fallback_font = _load_font(resolved_min_size, bold=bold)
    fallback_wrapped = _wrap_text(draw, text, fallback_font, max_width)
    return fallback_wrapped, fallback_font, resolved_min_spacing


def _measure_multiline_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    spacing: int,
) -> tuple[int, int]:
    text_box = _measure_draw().multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    return text_box[2] - text_box[0], text_box[3] - text_box[1]


def _fit_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    base_size: int,
    *,
    bold: bool = False,
    spacing: int = 8,
    min_size: int = 24,
    min_spacing: int = 4,
) -> tuple[str, ImageFont.ImageFont, int, int, int]:
    wrapped, font, line_spacing = _fit_wrapped_text(
        draw,
        text,
        max_width,
        max_height,
        base_size,
        bold=bold,
        spacing=spacing,
        min_size=min_size,
        min_spacing=min_spacing,
    )
    text_width, text_height = _measure_multiline_text(draw, wrapped, font, line_spacing)
    return wrapped, font, line_spacing, text_width, text_height


def _fitted_card_bottom(content_top: int, content_height: int, maximum: int, padding: int = 72) -> int:
    """Card bottom that hugs the copy instead of leaving a fixed panel half empty."""
    return min(content_top + content_height + padding, maximum)


def _stack_top(region_top: int, region_bottom: int, item_heights: list[int], gaps: list[int] | None = None) -> int:
    resolved_gaps = gaps or []
    total_height = sum(item_heights) + sum(resolved_gaps)
    region_height = max(region_bottom - region_top, total_height)
    return region_top + max((region_height - total_height) // 2, 0)


def _slam_body_max_height(body_card_top: int) -> int:
    return max(180, 1688 - body_card_top - 162)


def _slam_body_layout(body_card_top: int, body_height: int) -> tuple[int, int]:
    body_card_height = max(420, 114 + body_height + 48)
    body_card_bottom = min(1688, body_card_top + body_card_height)
    body_region_top = body_card_top + 114
    body_region_bottom = body_card_bottom - 48
    body_y = body_region_top + max((body_region_bottom - body_region_top - body_height) // 2, 0)
    return body_y, body_card_bottom


def _shifted_clear_of(
    box: tuple[int, int, int, int],
    obstacle: tuple[int, int, int, int],
    *,
    gap: int = 16,
    canvas_width: int = 1080,
    margin: int = 24,
) -> tuple[int, int, int, int]:
    """Slide box right until it clears obstacle, if the two actually overlap.

    Returns box unchanged when there is no overlap, and refuses to push it off
    the canvas: a badge half outside the frame is worse than one that touches.
    """
    if box[0] >= obstacle[2] or box[2] <= obstacle[0]:
        return box
    if box[1] >= obstacle[3] or box[3] <= obstacle[1]:
        return box
    shift = obstacle[2] + gap - box[0]
    if box[2] + shift > canvas_width - margin:
        return box
    return _offset_box(box, dx=shift)


def _avoid_title_panel_box(
    content_package: ContentPackage,
    box: tuple[int, int, int, int],
    *,
    gap: int = 24,
    padding: int = 24,
    canvas_height: int = 1920,
) -> tuple[int, int, int, int]:
    panel = _title_layout(content_package)["panel"]
    forbidden_top = max(padding, panel[1] - gap)
    forbidden_bottom = min(canvas_height - padding, panel[3] + gap)
    box_height = box[3] - box[1]
    min_top = padding
    max_top = max(padding, canvas_height - padding - box_height)
    base_top = min(max(box[1], min_top), max_top)

    candidate_tops = {
        base_top,
        min(max(panel[1] - gap - box_height, min_top), max_top),
        min(max(panel[3] + gap, min_top), max_top),
    }

    def overlap_length(top: int) -> int:
        bottom = top + box_height
        return max(0, min(bottom, forbidden_bottom) - max(top, forbidden_top))

    best_top = min(candidate_tops, key=lambda top: (overlap_length(top), abs(top - base_top)))
    return _offset_box(box, dy=best_top - box[1])


def _scene_top_clearance(content_package: ContentPackage, gap: int = 24) -> int:
    return _title_layout(content_package)["panel"][3] + gap


def _scene_top_shift(content_package: ContentPackage, top: int, gap: int = 24) -> int:
    return max(0, _scene_top_clearance(content_package, gap) - top)


def _slam_label_box(content_package: ContentPackage) -> tuple[int, int, int, int]:
    return _avoid_title_panel_box(content_package, (80, 520, 330, 604))


def _seed_choice(seed: int, salt: str, count: int) -> int:
    """Independent draws from one seed.

    _layout_variant_index already takes seed % 3 and the character composition
    seed % 8. A new axis on a bare seed % n would track those exactly and
    collapse the variation space, so each axis gets its own salt.
    """
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count


def _palette(content_package: ContentPackage) -> Palette:
    """The colourway for this post.

    Seeded without the MBTI type, so all 16 types of a series share it and a
    series still reads as one set.
    """
    variants = GROUP_PALETTE_VARIANTS[content_package.group_name]
    seed = _visual_seed(content_package, include_mbti=False)
    return variants[_seed_choice(seed, "palette", len(variants))]


def _style_offset(content_package: ContentPackage) -> int:
    seed = f"{content_package.series_name}|{content_package.format_name}|{content_package.theme}"
    return sum(ord(char) for char in seed) % 5


def _visual_seed(content_package: ContentPackage, *, include_mbti: bool = True) -> int:
    parts = [content_package.series_name, content_package.format_name, content_package.theme]
    if include_mbti:
        parts.append(content_package.mbti_type)
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _topic_visual_key(content_package: ContentPackage) -> str:
    """Return the main illustration direction for a topic, not merely its color motif."""
    label = f"{content_package.series_name} {content_package.format_name} {content_package.theme}"
    rules = (
        ("message", ("LINE", "返信", "連絡", "メッセージ")),
        ("approach", ("距離", "近づ", "縮め")),
        ("trust", ("心を許", "本音", "信頼")),
        ("shelter", ("しんどい", "ストレス", "限界", "不調", "SOS")),
        ("target", ("攻略", "刺さる", "効く", "接し方")),
        ("circle", ("友達", "仲良", "人間関係", "素の反応")),
        ("work", ("仕事", "職場", "働")),
        ("recharge", ("回復", "休み", "充電", "整え")),
        ("dialogue", ("会話", "話し方", "コミュニケーション")),
        ("signal", ("脈あり", "好意", "サイン")),
        ("affection", ("好きな人", "本命", "恋愛")),
    )
    for key, tokens in rules:
        if any(token in label for token in tokens):
            return key
    return "portrait"


def _visual_identity(content_package: ContentPackage) -> dict[str, object]:
    topic_seed = _visual_seed(content_package, include_mbti=False)
    mbti_seed = _visual_seed(content_package, include_mbti=True)
    return {
        # 5: palettes went from four fixed triples to 24 seeded ones, and the
        # renderer moved to 2x supersampling. Anything from 4 looks different.
        "version": 5,
        "topic_key": hashlib.sha1(
            f"{content_package.series_name}|{content_package.format_name}|{content_package.theme}".encode("utf-8")
        ).hexdigest()[:12],
        "illustration_direction": _topic_visual_key(content_package),
        "topic_composition": topic_seed % 8,
        "mbti_type": content_package.mbti_type,
        "mbti_variant": mbti_seed % 16,
        "source_policy": "provided-material-only",
        "thumbnail_scene": 1,
        "content_scene_start": 2,
        "thumbnail_theme_label": False,
        "design_tier": "deluxe",
        "group_palette": content_package.group_name,
        "palette": _palette(content_package).name,
        "render_scale": RENDER_SCALE,
        "chrome": _chrome_plan(topic_seed)["treatment"],
    }


ALL_MOTIFS = frozenset({"chat", "grid", "pulse", "orbit", "ribbon", "editorial"})
ILLUSTRATED_MOTIFS = ALL_MOTIFS - {"editorial"}
# Roughly one topic in four, so the feed alternates rather than turning over
# to photography. The pool is four photographs; until it grows, a higher share
# would repeat them visibly.
EDITORIAL_SHARE = 4


def _motif_key(content_package: ContentPackage, available: frozenset[str] = ILLUSTRATED_MOTIFS) -> str:
    if "editorial" in available and _seed_choice(
        _visual_seed(content_package, include_mbti=False), "editorial", EDITORIAL_SHARE
    ) == 0:
        # Assigned by seed rather than by keyword: the editorial look is a tone
        # choice, not a subject one, and matching Japanese substrings would fire
        # it on exactly the topics that already have a motif.
        return "editorial"

    label = f"{content_package.format_name} {content_package.theme}"
    if any(token in label for token in ("LINE", "返信", "連絡", "メッセージ")):
        return "chat"
    if any(token in label for token in ("攻略", "刺さる", "効く")):
        return "grid"
    if any(token in label for token in ("心理", "しんどい", "限界", "不調")):
        return "pulse"
    if any(token in label for token in ("人間関係", "信頼", "本音", "心を許")):
        return "orbit"
    return "ribbon"


def _is_pulse_layout(content_package: ContentPackage) -> bool:
    return _motif_key(content_package) == "pulse"


# Long enough for the most scenes a topic can produce. wrapup is absent from
# the interior: _scene_style_key already forces it on the last content slide,
# and with more than five scenes a five-entry cycle put a second one mid
# carousel.
SCENE_STYLE_CYCLES = {
    "chat": ["chat", "bottom_board", "chat", "spotlight", "bottom_board", "chat", "slam", "spotlight"],
    "grid": ["slam", "spotlight", "bottom_board", "slam", "spotlight", "bottom_board", "slam", "chat"],
    "pulse": ["spotlight", "bottom_board", "slam", "spotlight", "bottom_board", "slam", "spotlight", "chat"],
    "orbit": ["spotlight", "chat", "bottom_board", "slam", "chat", "spotlight", "bottom_board", "slam"],
    "ribbon": ["spotlight", "bottom_board", "chat", "slam", "spotlight", "chat", "bottom_board", "slam"],
}
SCENE_STYLE_CYCLE_LENGTH = 8


def _scene_style_index(content_package: ContentPackage, scene_index: int) -> int:
    content_scene_index = _content_scene_index(content_package, scene_index)
    return (content_scene_index + _style_offset(content_package)) % SCENE_STYLE_CYCLE_LENGTH


def _scene_style_key(content_package: ContentPackage, scene: Scene, scene_index: int) -> str:
    if _is_closer_scene(content_package, scene, scene_index):
        return "closer"

    content_scene_index = _content_scene_index(content_package, scene_index)
    scene_total = _content_scene_total(content_package)
    if content_scene_index == scene_total - 1:
        return "wrapup"

    cycle = SCENE_STYLE_CYCLES[_motif_key(content_package)]
    return cycle[_scene_style_index(content_package, scene_index) % len(cycle)]


def _offset_box(box: tuple[int, int, int, int], dx: int = 0, dy: int = 0) -> tuple[int, int, int, int]:
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def _adjust_box(
    box: tuple[int, int, int, int],
    *,
    left: int = 0,
    top: int = 0,
    right: int = 0,
    bottom: int = 0,
) -> tuple[int, int, int, int]:
    return (box[0] + left, box[1] + top, box[2] + right, box[3] + bottom)


def _layout_variant_index(content_package: ContentPackage) -> int:
    return _visual_seed(content_package, include_mbti=False) % 3


def _variantize_layout_profile(
    profile: LayoutProfile,
    *,
    title_shift: tuple[int, int],
    thumbnail_shift: tuple[int, int],
    character_shift: tuple[int, int],
    title_panel_adjust: tuple[int, int, int, int] = (0, 0, 0, 0),
    thumbnail_card_adjust: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> LayoutProfile:
    return LayoutProfile(
        title_panel=_adjust_box(
            _offset_box(profile.title_panel, dx=title_shift[0], dy=title_shift[1]),
            left=title_panel_adjust[0],
            top=title_panel_adjust[1],
            right=title_panel_adjust[2],
            bottom=title_panel_adjust[3],
        ),
        title_label_left=_offset_box(profile.title_label_left, dx=title_shift[0], dy=title_shift[1]),
        title_label_right=_offset_box(profile.title_label_right, dx=title_shift[0], dy=title_shift[1]),
        title_content_region=_offset_box(profile.title_content_region, dx=title_shift[0], dy=title_shift[1]),
        title_hook_inset=profile.title_hook_inset,
        thumbnail_card=_adjust_box(
            _offset_box(profile.thumbnail_card, dx=thumbnail_shift[0], dy=thumbnail_shift[1]),
            left=thumbnail_card_adjust[0],
            top=thumbnail_card_adjust[1],
            right=thumbnail_card_adjust[2],
            bottom=thumbnail_card_adjust[3],
        ),
        thumbnail_label_left=_offset_box(profile.thumbnail_label_left, dx=thumbnail_shift[0], dy=thumbnail_shift[1]),
        thumbnail_label_right=_offset_box(profile.thumbnail_label_right, dx=thumbnail_shift[0], dy=thumbnail_shift[1]),
        thumbnail_content_region=_offset_box(profile.thumbnail_content_region, dx=thumbnail_shift[0], dy=thumbnail_shift[1]),
        character_box=_offset_box(profile.character_box, dx=character_shift[0], dy=character_shift[1]),
        density_axis=profile.density_axis,
        density_shift=profile.density_shift,
    )


def _apply_layout_variant(profile: LayoutProfile, content_package: ContentPackage) -> LayoutProfile:
    variant = _layout_variant_index(content_package)
    pin_pulse_character = _motif_key(content_package) == "pulse"

    def finalize(resolved_profile: LayoutProfile) -> LayoutProfile:
        if pin_pulse_character:
            return replace(resolved_profile, character_box=PULSE_CHARACTER_BOX)
        return resolved_profile

    if variant == 0:
        return finalize(profile)

    if profile.density_axis == "vertical":
        if variant == 1:
            return finalize(
                _variantize_layout_profile(
                    profile,
                    title_shift=(0, -72),
                    thumbnail_shift=(20, 40),
                    character_shift=(-48, -36),
                    title_panel_adjust=(-12, -8, 20, 24),
                    thumbnail_card_adjust=(-6, 0, 18, 26),
                )
            )
        return finalize(
            _variantize_layout_profile(
                profile,
                title_shift=(18, 54),
                thumbnail_shift=(-24, -26),
                character_shift=(42, 24),
                title_panel_adjust=(-18, 0, 12, 22),
                thumbnail_card_adjust=(-18, -16, 8, 18),
            )
        )

    if variant == 1:
        return finalize(
            _variantize_layout_profile(
                profile,
                title_shift=(-40, 22),
                thumbnail_shift=(26, 34),
                character_shift=(-64, 28),
                title_panel_adjust=(-18, -6, 26, 18),
                thumbnail_card_adjust=(-10, 0, 24, 24),
            )
        )
    return finalize(
        _variantize_layout_profile(
            profile,
            title_shift=(34, -18),
            thumbnail_shift=(-22, -14),
            character_shift=(48, -42),
            title_panel_adjust=(-8, -12, 18, 24),
            thumbnail_card_adjust=(-18, -12, 10, 18),
        )
    )


def _layout_density_score(content_package: ContentPackage) -> int:
    """How much room this topic's copy wants.

    Every input has to be fixed by the topic, because all 16 types of a series
    must lay out identically. Scoring the per-type bodies broke that: the
    lengths differ by a character or two and the panel moved with them, which
    quantising only hid until a topic landed on a step boundary.
    """
    title_weight = len(content_package.title.replace("\n", ""))
    series_weight = len(content_package.series_name.replace("\n", ""))
    return title_weight * 2 + series_weight * 2 + _content_scene_total(content_package) * 8


def _base_layout_profile(content_package: ContentPackage) -> LayoutProfile:
    variant = _motif_key(content_package)
    if variant == "grid":
        return LayoutProfile(
            title_panel=(48, 1010, 646, 1810),
            title_label_left=(82, 1052, 344, 1132),
            title_label_right=(386, 1052, 610, 1132),
            title_content_region=(86, 1188, 606, 1688),
            title_hook_inset=(28, 16),
            thumbnail_card=(48, 830, 734, 1780),
            thumbnail_label_left=(74, 876, 336, 954),
            thumbnail_label_right=(440, 876, 690, 954),
            thumbnail_content_region=(86, 1018, 682, 1650),
            character_box=(666, 110, 1038, 990),
            density_axis="vertical",
            density_shift=42,
        )
    if variant == "pulse":
        return LayoutProfile(
            title_panel=(56, 920, 692, 1722),
            title_label_left=(90, 964, 360, 1044),
            title_label_right=(402, 964, 656, 1044),
            title_content_region=(94, 1098, 652, 1604),
            title_hook_inset=(28, 16),
            thumbnail_card=(62, 920, 760, 1772),
            thumbnail_label_left=(90, 962, 350, 1040),
            thumbnail_label_right=(466, 962, 716, 1040),
            thumbnail_content_region=(98, 1106, 708, 1646),
            character_box=PULSE_CHARACTER_BOX,
            density_axis="vertical",
            density_shift=36,
        )
    if variant == "orbit":
        return LayoutProfile(
            title_panel=(82, 180, 700, 760),
            title_label_left=(118, 220, 388, 300),
            title_label_right=(432, 220, 666, 300),
            title_content_region=(122, 356, 662, 686),
            title_hook_inset=(28, 16),
            thumbnail_card=(88, 230, 760, 1380),
            thumbnail_label_left=(118, 270, 388, 348),
            thumbnail_label_right=(470, 270, 724, 348),
            thumbnail_content_region=(122, 414, 712, 1240),
            character_box=(706, 280, 1030, 1440),
            density_axis="horizontal",
            density_shift=34,
        )
    if variant == "chat":
        return LayoutProfile(
            title_panel=(52, 116, 682, 704),
            title_label_left=(86, 154, 348, 234),
            title_label_right=(392, 154, 646, 234),
            title_content_region=(92, 286, 642, 640),
            title_hook_inset=(28, 16),
            thumbnail_card=(52, 170, 700, 1320),
            thumbnail_label_left=(78, 208, 340, 286),
            thumbnail_label_right=(430, 208, 674, 286),
            thumbnail_content_region=(88, 356, 648, 1198),
            character_box=(728, 470, 1038, 1540),
            density_axis="horizontal",
            density_shift=40,
        )
    return LayoutProfile(
        title_panel=(56, 162, 748, 596),
        title_label_left=(82, 194, 474, 274),
        title_label_right=(492, 194, 714, 274),
        title_content_region=(88, 318, 708, 560),
        title_hook_inset=(34, 12),
        thumbnail_card=(58, 228, 760, 1216),
        thumbnail_label_left=(64, 76, 454, 154),
        thumbnail_label_right=(734, 76, 1016, 154),
        thumbnail_content_region=(92, 318, 706, 1120),
        character_box=(630, 380, 1040, 1560),
        density_axis="horizontal",
        density_shift=28,
    )


def _layout_profile(content_package: ContentPackage) -> LayoutProfile:
    profile = _base_layout_profile(content_package)
    density = _layout_density_score(content_package)
    raw_shift = (density - 130) // 2
    shift = max(-profile.density_shift, min(profile.density_shift, raw_shift))

    if profile.density_axis == "vertical":
        density_profile = LayoutProfile(
            title_panel=_offset_box(profile.title_panel, dy=shift),
            title_label_left=_offset_box(profile.title_label_left, dy=shift),
            title_label_right=_offset_box(profile.title_label_right, dy=shift),
            title_content_region=_offset_box(profile.title_content_region, dy=shift),
            title_hook_inset=profile.title_hook_inset,
            thumbnail_card=_offset_box(profile.thumbnail_card, dy=shift),
            thumbnail_label_left=_offset_box(profile.thumbnail_label_left, dy=shift),
            thumbnail_label_right=_offset_box(profile.thumbnail_label_right, dy=shift),
            thumbnail_content_region=_offset_box(profile.thumbnail_content_region, dy=shift),
            character_box=_offset_box(profile.character_box, dy=-shift // 2),
            density_axis=profile.density_axis,
            density_shift=profile.density_shift,
        )
        return _apply_layout_variant(density_profile, content_package)

    density_profile = LayoutProfile(
        title_panel=_offset_box(profile.title_panel, dx=shift),
        title_label_left=_offset_box(profile.title_label_left, dx=shift),
        title_label_right=_offset_box(profile.title_label_right, dx=shift),
        title_content_region=_offset_box(profile.title_content_region, dx=shift),
        title_hook_inset=profile.title_hook_inset,
        thumbnail_card=_offset_box(profile.thumbnail_card, dx=shift),
        thumbnail_label_left=_offset_box(profile.thumbnail_label_left, dx=shift),
        thumbnail_label_right=_offset_box(profile.thumbnail_label_right, dx=shift),
        thumbnail_content_region=_offset_box(profile.thumbnail_content_region, dx=shift),
        character_box=_offset_box(profile.character_box, dx=-shift // 2),
        density_axis=profile.density_axis,
        density_shift=profile.density_shift,
    )
    return _apply_layout_variant(density_profile, content_package)


def _title_layout(content_package: ContentPackage) -> dict[str, tuple[int, int, int, int] | tuple[int, int]]:
    profile = _layout_profile(content_package)
    return {
        "panel": profile.title_panel,
        "label_left": profile.title_label_left,
        "label_right": profile.title_label_right,
        "content_region": profile.title_content_region,
        "hook_inset": profile.title_hook_inset,
    }


def _thumbnail_layout(content_package: ContentPackage) -> dict[str, tuple[int, int, int, int] | tuple[int, int]]:
    profile = _layout_profile(content_package)
    return {
        "card": profile.thumbnail_card,
        "label_left": profile.thumbnail_label_left,
        "label_right": profile.thumbnail_label_right,
        "content_region": profile.thumbnail_content_region,
    }


def _character_box(content_package: ContentPackage) -> tuple[int, int, int, int]:
    return _layout_profile(content_package).character_box


# Content slides keep the character in the upper right, clear of the copy
# cards that own the lower two thirds. The thumbnail box is much taller, so
# only its horizontal placement carries over - that is the part that varies by
# motif, and using one hardcoded box made every motif's body slides identical.
CONTENT_CHARACTER_TOP = 190
CONTENT_CHARACTER_BOTTOM = 980


def _scene_character_box(content_package: ContentPackage, scene_index: int) -> tuple[int, int, int, int]:
    if scene_index == 0 or _is_pulse_layout(content_package):
        return _character_box(content_package)
    thumbnail_box = _character_box(content_package)
    left = min(max(thumbnail_box[0], 636), 764)
    right = min(max(thumbnail_box[2], left + 290), 1044)
    # A small drift down the carousel so consecutive slides are not stamped
    # from the same position.
    drift = (_visual_seed(content_package) // 7 + scene_index * 13) % 40 - 20
    return (left, CONTENT_CHARACTER_TOP + drift, right, CONTENT_CHARACTER_BOTTOM + drift)


def _resolve_illustration_path(config: AppConfig, mbti_type: str) -> Path | None:
    roots = [config.assets_dir, config.official_images_dir]
    for root in roots:
        if not root.exists():
            continue
        for stem in (mbti_type, mbti_type.lower(), mbti_type.upper()):
            for suffix in (".png", ".jpg", ".jpeg", ".webp"):
                candidate = root / f"{stem}{suffix}"
                if candidate.exists():
                    return candidate
        for candidate in root.iterdir():
            if candidate.is_file() and candidate.stem.lower() == mbti_type.lower():
                return candidate
    return None


def _draw_heart(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    size: int,
    fill: tuple[int, int, int, int],
) -> None:
    x, y = center
    radius = max(size // 4, 2)
    draw.ellipse((x - size // 2, y - size // 2, x, y), fill=fill)
    draw.ellipse((x, y - size // 2, x + size // 2, y), fill=fill)
    draw.polygon(((x - size // 2, y - size // 4), (x + size // 2, y - size // 4), (x, y + size // 2)), fill=fill)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _draw_topic_illustration_stage(
    image: Image.Image,
    box: tuple[int, int, int, int],
    accent: str,
    light: str,
    content_package: ContentPackage,
) -> None:
    """Draw topic-specific scenery so a reused source character becomes a new illustration."""
    draw = ScaledDraw(image)
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    key = _topic_visual_key(content_package)
    variant = _visual_seed(content_package, include_mbti=False) % 8
    accent_rgba = _hex_to_rgba(accent, 178)
    light_rgba = _hex_to_rgba(light, 190)
    faint = _hex_to_rgba(light, 74)

    if key in {"signal", "affection"}:
        for index, (dx, dy) in enumerate(((-34, 96), (width - 38, 170), (width - 2, height // 2))):
            _draw_heart(draw, (left + dx, top + dy), 36 + index * 10, light_rgba if index != 1 else accent_rgba)
        for radius in (52, 88, 124):
            draw.ellipse((right - radius - 18, top + 34 - radius, right + radius - 18, top + 34 + radius), outline=faint, width=4)
    elif key == "approach":
        step_y = bottom - 92
        for index in range(4):
            step_left = left - 34 + index * max(width // 4, 38)
            draw.rounded_rectangle((step_left, step_y - index * 42, step_left + 108, step_y + 42 - index * 42), radius=18, fill=_hex_to_rgba(light, 62 + index * 24))
        draw.line((left - 8, top + height // 2, right + 40, top + 84), fill=light_rgba, width=9)
        draw.polygon(((right + 40, top + 84), (right - 10, top + 76), (right + 22, top + 126)), fill=light_rgba)
    elif key == "trust":
        shield = ((left - 42, top + 90), (left + 86, top + 54), (left + 114, top + 196), (left + 22, top + 278), (left - 64, top + 196))
        draw.polygon(shield, fill=_hex_to_rgba(accent, 112), outline=light_rgba)
        draw.arc((left - 22, top + 104, left + 64, top + 194), 180, 360, fill=light_rgba, width=9)
        draw.rounded_rectangle((left - 18, top + 146, left + 60, top + 232), radius=18, fill=_hex_to_rgba(light, 142))
        draw.ellipse((left + 8, top + 168, left + 34, top + 194), fill=accent_rgba)
        draw.line((left + 21, top + 190, left + 21, top + 214), fill=accent_rgba, width=7)
    elif key == "message":
        phone = (right - 116, top + 20, right + 34, top + 302)
        draw.rounded_rectangle(phone, radius=30, fill=_hex_to_rgba(light, 70), outline=light_rgba, width=6)
        draw.rounded_rectangle((phone[0] + 18, phone[1] + 46, phone[2] - 18, phone[3] - 42), radius=18, fill=_hex_to_rgba(accent, 86))
        for index in range(3):
            bubble_left = left - 54 + (index % 2) * 44
            bubble_top = top + 120 + index * 96
            draw.rounded_rectangle((bubble_left, bubble_top, bubble_left + 154, bubble_top + 64), radius=24, fill=_hex_to_rgba(light, 80 + index * 24))
    elif key == "shelter":
        canopy_y = top + 92
        draw.pieslice((left - 76, canopy_y, right + 80, canopy_y + 300), 180, 360, fill=_hex_to_rgba(light, 104), outline=light_rgba, width=5)
        draw.line((left + width // 2, canopy_y + 148, left + width // 2, bottom - 28), fill=light_rgba, width=9)
        draw.arc((left + width // 2 - 8, bottom - 92, left + width // 2 + 72, bottom - 12), 0, 180, fill=light_rgba, width=9)
        for index in range(4):
            rain_x = left - 36 + index * max(width // 3, 40)
            draw.line((rain_x, top + 32, rain_x - 34, top + 98), fill=faint, width=6)
    elif key == "target":
        center = (right - 6, top + 136)
        for radius in (42, 82, 122):
            draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=light_rgba if radius == 42 else faint, width=6)
        draw.line((left - 56, bottom - 28, center[0], center[1]), fill=accent_rgba, width=8)
        draw.polygon(((center[0], center[1]), (center[0] - 42, center[1] + 5), (center[0] - 6, center[1] + 40)), fill=accent_rgba)
    elif key == "circle":
        nodes = ((left - 24, top + 128), (right + 18, top + 82), (right + 44, bottom - 150), (left - 10, bottom - 66))
        for first, second in zip(nodes, nodes[1:] + nodes[:1]):
            draw.line((*first, *second), fill=faint, width=6)
        for index, (x, y) in enumerate(nodes):
            radius = 28 + (index + variant) % 3 * 8
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=light_rgba if index % 2 else accent_rgba)
    elif key == "work":
        desk_y = bottom - 84
        draw.rounded_rectangle((left - 70, desk_y, right + 68, desk_y + 32), radius=14, fill=light_rgba)
        draw.line((left - 6, desk_y + 30, left - 28, bottom + 32), fill=light_rgba, width=12)
        draw.line((right + 6, desk_y + 30, right + 28, bottom + 32), fill=light_rgba, width=12)
        chart = (right - 132, top + 36, right + 34, top + 204)
        draw.rounded_rectangle(chart, radius=20, fill=_hex_to_rgba(light, 62), outline=light_rgba, width=5)
        points = [(chart[0] + 24, chart[3] - 34), (chart[0] + 62, chart[1] + 94), (chart[0] + 104, chart[1] + 112), (chart[2] - 20, chart[1] + 34)]
        draw.line(points, fill=accent_rgba, width=8, joint="curve")
    elif key == "recharge":
        moon_box = (right - 112, top + 12, right + 54, top + 178)
        draw.ellipse(moon_box, fill=light_rgba)
        draw.ellipse((moon_box[0] + 48, moon_box[1] - 12, moon_box[2] + 30, moon_box[3] - 36), fill=(0, 0, 0, 0))
        for point in ((left - 14, top + 112), (right + 20, top + 256), (left + 26, bottom - 134)):
            _draw_spark(draw, point, 22, accent_rgba)
        draw.arc((left - 48, bottom - 220, left + 116, bottom - 24), 190, 350, fill=light_rgba, width=12)
        draw.arc((left - 8, bottom - 230, left + 154, bottom - 42), 150, 310, fill=accent_rgba, width=10)
    elif key == "dialogue":
        bubbles = ((left - 78, top + 58, left + 100, top + 180), (right - 68, top + 174, right + 72, top + 286))
        for index, bubble in enumerate(bubbles):
            color = _hex_to_rgba(light, 104 + index * 38)
            draw.rounded_rectangle(bubble, radius=34, fill=color, outline=light_rgba, width=4)
            tail_x = bubble[2] - 42 if index == 0 else bubble[0] + 32
            draw.polygon(((tail_x, bubble[3] - 4), (tail_x + 42, bubble[3] - 4), (tail_x + (30 if index == 0 else 8), bubble[3] + 38)), fill=color)
    else:
        for offset in range(3):
            inset = 18 + offset * 34
            draw.rounded_rectangle((left - inset, top - inset, right + inset, bottom + inset), radius=74 + offset * 18, outline=_hex_to_rgba(light, 78 - offset * 14), width=5)


# accent is tuned to be bright against the background, which leaves it far too
# light to carry white text: 1.57:1 for 探検家, 2.00:1 for 番人. Pills that hold
# white copy use the deeper partner instead. Keyed on the accent because all 24
# are distinct, which keeps accent_deep out of a dozen function signatures.
_ACCENT_DEEP_BY_ACCENT = {
    palette.accent: palette.accent_deep
    for variants in GROUP_PALETTE_VARIANTS.values()
    for palette in variants
}


def _pill_fill(accent: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return _hex_to_rgba(_ACCENT_DEEP_BY_ACCENT.get(accent, accent), alpha)


def _draw_label(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill, text_fill) -> None:
    draw.rounded_rectangle(box, radius=34, fill=fill)
    text_box = _measure_draw().textbbox((0, 0), text, font=font)
    text_x = box[0] + ((box[2] - box[0]) - (text_box[2] - text_box[0])) // 2
    text_y = box[1] + ((box[3] - box[1]) - (text_box[3] - text_box[1])) // 2 - 2
    draw.text((text_x, text_y), text, font=font, fill=text_fill)


def _draw_shadowed_round_box(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    shadow_alpha: int = 120,
) -> None:
    canvas = ScaledDraw(image)
    shadow_layer = canvas.layer()
    shadow_draw = canvas.sub(shadow_layer)
    shadow_draw.rounded_rectangle(
        (box[0] + 10, box[1] + 16, box[2] + 10, box[3] + 16),
        radius=radius,
        fill=(0, 0, 0, shadow_alpha),
    )
    shadow_layer = shadow_layer.filter(canvas.blur(22))
    image.alpha_composite(shadow_layer)
    canvas.rounded_rectangle(box, radius=radius, fill=fill)


def _draw_luxury_round_box(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    accent: str,
    light: str,
    shadow_alpha: int = 150,
) -> None:
    """Draw a layered premium card with glow, bevel lines, and corner jewels."""
    canvas = ScaledDraw(image)
    glow_layer = canvas.layer()
    glow_draw = canvas.sub(glow_layer)
    glow_draw.rounded_rectangle(
        (box[0] - 5, box[1] - 5, box[2] + 5, box[3] + 5),
        radius=radius + 5,
        outline=_hex_to_rgba(light, 118),
        width=12,
    )
    glow_layer = glow_layer.filter(canvas.blur(18))
    image.alpha_composite(glow_layer)

    _draw_shadowed_round_box(image, box, radius, fill, shadow_alpha)
    card_draw = ScaledDraw(image)
    card_draw.rounded_rectangle(box, radius=radius, outline=_hex_to_rgba(light, 170), width=4)
    inner = (box[0] + 11, box[1] + 11, box[2] - 11, box[3] - 11)
    card_draw.rounded_rectangle(inner, radius=max(radius - 11, 8), outline=(255, 255, 255, 48), width=2)
    card_draw.line(
        (box[0] + radius, box[1] + 5, box[2] - radius, box[1] + 5),
        fill=(255, 255, 255, 98),
        width=3,
    )

    jewel_size = 11
    for x, y in ((box[0] + 30, box[1] + 30), (box[2] - 30, box[3] - 30)):
        card_draw.polygon(
            ((x, y - jewel_size), (x + jewel_size, y), (x, y + jewel_size), (x - jewel_size, y)),
            fill=_hex_to_rgba(accent, 220),
            outline=_hex_to_rgba(light, 235),
        )


def _draw_luxury_divider(
    draw: ImageDraw.ImageDraw,
    left: int,
    right: int,
    y: int,
    accent: str,
    light: str,
) -> None:
    center = (left + right) // 2
    draw.line((left, y, center - 34, y), fill=_hex_to_rgba(light, 138), width=3)
    draw.line((center + 34, y, right, y), fill=_hex_to_rgba(light, 138), width=3)
    draw.line((left + 34, y + 8, center - 46, y + 8), fill=(255, 255, 255, 42), width=2)
    draw.line((center + 46, y + 8, right - 34, y + 8), fill=(255, 255, 255, 42), width=2)
    draw.polygon(
        ((center, y - 19), (center + 19, y), (center, y + 19), (center - 19, y)),
        fill=_hex_to_rgba(accent, 232),
        outline=_hex_to_rgba(light, 245),
    )
    draw.ellipse((center - 5, y - 5, center + 5, y + 5), fill=(255, 255, 255, 230))


def _has_thumbnail_scene(content_package: ContentPackage) -> bool:
    return bool(content_package.scenes) and content_package.scenes[0].title == content_package.title and content_package.scenes[0].body == content_package.hook


def _content_scene_total(content_package: ContentPackage) -> int:
    total = len(content_package.scenes)
    if _has_thumbnail_scene(content_package):
        total -= 1
    if _has_closer_scene(content_package):
        total -= 1
    return max(total, 1)


def _content_scene_index(content_package: ContentPackage, scene_index: int) -> int:
    return scene_index - 1 if _has_thumbnail_scene(content_package) else scene_index


def _is_thumbnail_scene(content_package: ContentPackage, scene: Scene, scene_index: int) -> bool:
    return _has_thumbnail_scene(content_package) and scene_index == 0 and scene.title == content_package.title and scene.body == content_package.hook


def _has_closer_scene(content_package: ContentPackage) -> bool:
    return bool(content_package.scenes) and content_package.scenes[-1].title == CLOSER_SCENE_TITLE and content_package.scenes[-1].body == CLOSER_SCENE_BODY


def _is_closer_scene(content_package: ContentPackage, scene: Scene, scene_index: int) -> bool:
    return _has_closer_scene(content_package) and scene_index == len(content_package.scenes) - 1 and scene.title == CLOSER_SCENE_TITLE and scene.body == CLOSER_SCENE_BODY


def _draw_thumbnail_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    layout = _thumbnail_layout(content_package)
    card = layout["card"]
    label_left = layout["label_left"]
    label_right = layout["label_right"]
    content_region = layout["content_region"]

    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        content_package.title,
        content_region[2] - content_region[0] - 24,
        max(content_region[3] - content_region[1] - 160, 300),
        98,
        bold=True,
        spacing=16,
        min_size=62,
        min_spacing=8,
    )
    title_area_top = max(content_region[1], label_left[3] + 76)
    # The old 760px floor held the cover card open well past the title, leaving
    # a slab of empty panel under short headlines.
    card_bottom = min(card[3], max(card[1] + 430, title_area_top + title_height + 174))
    cover_card = (card[0], card[1], card[2], card_bottom)
    _draw_luxury_round_box(image, cover_card, 72, (8, 15, 38, 188), accent, light, 168)
    draw = ScaledDraw(image)
    draw.rounded_rectangle(
        (cover_card[0] + 22, title_area_top - 16, cover_card[0] + 30, card_bottom - 104),
        radius=4,
        fill=_hex_to_rgba(accent, 225),
    )
    title_area_bottom = card_bottom - 116
    title_y = title_area_top + max((title_area_bottom - title_area_top - title_height) // 2, 0)
    draw.multiline_text(
        (content_region[0] + 4, title_y + 7),
        title,
        font=title_font,
        fill=_hex_to_rgba(accent, 126),
        spacing=title_spacing,
    )
    draw.multiline_text((content_region[0], title_y), title, font=title_font, fill="white", spacing=title_spacing)
    _draw_luxury_divider(draw, content_region[0], content_region[2], card_bottom - 72, accent, light)
    _draw_label(
        draw,
        label_left,
        f"{content_package.mbti_type} / {content_package.archetype_name}",
        fonts["scene_tag"],
        _hex_to_rgba(background, 232),
        "white",
    )
    # The old COVER n/16 badge reported this post's place in the 16-type series,
    # which means nothing to someone seeing a single carousel. A swipe cue earns
    # the space instead.
    _draw_label(
        draw,
        label_right,
        "SWIPE →",
        fonts["scene_tag"],
        _pill_fill(accent, 220),
        "white",
    )


def _draw_content_header(
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    header_box = (54, 72, 650, 166)
    draw.rounded_rectangle((header_box[0] + 7, header_box[1] + 10, header_box[2] + 7, header_box[3] + 10), radius=42, fill=(0, 0, 0, 54))
    draw.rounded_rectangle(
        header_box,
        radius=42,
        fill=_hex_to_rgba(background, 222),
        outline=_hex_to_rgba(light, 176),
        width=4,
    )
    draw.rounded_rectangle(
        (header_box[0] + 7, header_box[1] + 7, header_box[2] - 7, header_box[3] - 7),
        radius=35,
        outline=(255, 255, 255, 38),
        width=2,
    )
    label = f"{content_package.mbti_type}  |  {content_package.format_name}"
    wrapped, font, spacing, _, text_height = _fit_text_block(
        draw,
        label,
        header_box[2] - header_box[0] - 48,
        header_box[3] - header_box[1] - 20,
        30,
        bold=True,
        spacing=4,
        min_size=24,
        min_spacing=2,
    )
    text_y = header_box[1] + max((header_box[3] - header_box[1] - text_height) // 2, 0) - 2
    draw.multiline_text((header_box[0] + 24, text_y), wrapped, font=font, fill="white", spacing=spacing)
    draw.ellipse((header_box[2] - 34, header_box[1] + 30, header_box[2] - 14, header_box[1] + 50), fill=_hex_to_rgba(accent))
    jewel_x = header_box[0] + 14
    jewel_y = (header_box[1] + header_box[3]) // 2
    draw.polygon(
        ((jewel_x, jewel_y - 8), (jewel_x + 8, jewel_y), (jewel_x, jewel_y + 8), (jewel_x - 8, jewel_y)),
        fill=_hex_to_rgba(light, 230),
    )

def _draw_scene_style_spotlight(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    scene_total: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    top_shift = _scene_top_shift(content_package, 560)
    card_top = 560 + top_shift
    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        500,
        168,
        52,
        bold=True,
        spacing=10,
        min_size=34,
        min_spacing=6,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        514,
        336,
        52,
        spacing=20,
        min_size=32,
        min_spacing=10,
    )
    content_top = card_top + 200
    card_bottom = _fitted_card_bottom(content_top, title_height + 42 + body_height, 1498 + top_shift)
    _draw_shadowed_round_box(image, (54, card_top, 712, card_bottom), 60, (255, 255, 255, 234))
    _draw_label(draw, _offset_box((94, 604, 408, 692), dy=top_shift), f"{scene_index + 1:02d} / {scene_total}", fonts["scene_tag"], accent, light)
    _draw_label(draw, _offset_box((454, 604, 670, 692), dy=top_shift), "POINT", fonts["scene_tag"], _hex_to_rgba(background, 220), "white")
    draw.multiline_text((96, content_top), title, font=title_font, fill=background, spacing=title_spacing)
    draw.multiline_text((96, content_top + title_height + 42), body, font=body_font, fill="#171717", spacing=body_spacing)


def _draw_scene_style_bottom_board(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    scene_total: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        760,
        180,
        60,
        bold=True,
        spacing=10,
        min_size=40,
        min_spacing=6,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        760,
        278,
        46,
        spacing=18,
        min_size=30,
        min_spacing=10,
    )
    content_top = 1216
    card_bottom = _fitted_card_bottom(content_top, title_height + 48 + body_height, 1768)
    _draw_shadowed_round_box(image, (44, 1040, 1036, card_bottom), 68, (10, 15, 35, 164), 150)
    draw.rounded_rectangle((78, 1080, 102, card_bottom - 78), radius=12, fill=_hex_to_rgba(light, 235))
    _draw_label(draw, (126, 1084, 390, 1170), f"SCENE {scene_index + 1}", fonts["scene_tag"], _pill_fill(accent, 210), "white")
    draw.multiline_text((126, content_top), title, font=title_font, fill="white", spacing=title_spacing)
    draw.multiline_text((126, content_top + title_height + 48), body, font=body_font, fill=(245, 245, 245), spacing=body_spacing)
    counter_text = f"{scene_index + 1:02d} / {scene_total}"
    text_box = _measure_draw().textbbox((0, 0), counter_text, font=fonts["count"])
    draw.text((944 - (text_box[2] - text_box[0]), 1108), counter_text, font=fonts["count"], fill=_hex_to_rgba(light, 230))


def _draw_scene_style_chat(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        504,
        176,
        52,
        bold=True,
        spacing=10,
        min_size=34,
        min_spacing=6,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        620,
        428,
        46,
        spacing=18,
        min_size=30,
        min_spacing=10,
    )
    bubble_a_height = max(270, title_height + 170)
    bubble_b_height = max(420, body_height + 200)
    top_shift = _scene_top_shift(content_package, 604)
    bubble_a = _offset_box((66, 604, 700, 604 + bubble_a_height), dy=top_shift)
    bubble_b_top = bubble_a[3] + 64
    bubble_b = (220, bubble_b_top, 994, bubble_b_top + bubble_b_height)
    _draw_shadowed_round_box(image, bubble_a, 58, (255, 255, 255, 240), 96)
    _draw_shadowed_round_box(image, bubble_b, 62, _hex_to_rgba(light, 228), 106)
    draw.polygon([(158, bubble_a[3] - 2), (210, bubble_a[3] + 38), (240, bubble_a[3] - 14)], fill=(255, 255, 255, 240))
    draw.polygon([(760, bubble_b[3] - 12), (816, bubble_b[3] + 24), (846, bubble_b[3] - 30)], fill=_hex_to_rgba(light, 228))
    _draw_label(draw, _offset_box((102, 634, 320, 714), dy=top_shift), f"{scene_index + 1:02d}", fonts["scene_tag"], _pill_fill(accent), "white")
    title_y = bubble_a[1] + max((bubble_a_height - title_height) // 2, 0) + 8
    body_y = bubble_b[1] + max((bubble_b_height - body_height) // 2, 0) - 6
    draw.multiline_text((104, title_y), title, font=title_font, fill=background, spacing=title_spacing)
    draw.multiline_text((258, body_y), body, font=body_font, fill=background, spacing=body_spacing)


def _draw_scene_style_slam(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    label_box = _slam_label_box(content_package)
    title, slam_font, slam_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        520,
        384,
        84,
        bold=True,
        spacing=2,
        min_size=52,
        min_spacing=0,
    )
    title_y = max(_stack_top(654, 1088, [title_height]), label_box[3] + 36)
    draw.multiline_text((78, title_y + 12), title, font=slam_font, fill=_hex_to_rgba(accent, 180), spacing=slam_spacing)
    draw.multiline_text((86, title_y), title, font=slam_font, fill="white", spacing=slam_spacing)
    _draw_label(draw, label_box, f"POINT {scene_index + 1}", fonts["scene_tag"], _hex_to_rgba(light, 214), background)
    body_card_top = max(1120, title_y + title_height + 96)
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        588,
        _slam_body_max_height(body_card_top),
        46,
        spacing=18,
        min_size=30,
        min_spacing=10,
    )
    body_y, body_card_bottom = _slam_body_layout(body_card_top, body_height)
    _draw_shadowed_round_box(image, (72, body_card_top, 822, body_card_bottom), 60, (255, 255, 255, 232), 110)
    # A short rule above the copy. At 394x48 this read as a label someone
    # forgot to fill in.
    draw.rounded_rectangle((112, body_card_top + 52, 232, body_card_top + 62), radius=5, fill=_hex_to_rgba(accent, 210))
    draw.multiline_text((112, body_y), body, font=body_font, fill="#191919", spacing=body_spacing)


def _draw_scene_style_wrapup(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    scene_total: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        708,
        204,
        60,
        bold=True,
        spacing=10,
        min_size=40,
        min_spacing=6,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        704,
        266,
        46,
        spacing=18,
        min_size=30,
        min_spacing=10,
    )
    content_top = 870
    card_bottom = _fitted_card_bottom(content_top, title_height + 54 + body_height, 1586)
    _draw_shadowed_round_box(image, (86, 676, 998, card_bottom), 68, (255, 255, 255, 226), 116)
    _draw_label(draw, (122, 716, 436, 802), f"{scene_index + 1:02d} / {scene_total}", fonts["scene_tag"], _pill_fill(accent), "white")
    _draw_label(draw, (690, 716, 958, 802), "CHECK", fonts["scene_tag"], _hex_to_rgba(light, 220), background)
    draw.multiline_text((124, content_top), title, font=title_font, fill=background, spacing=title_spacing)
    draw.multiline_text((124, content_top + title_height + 54), body, font=body_font, fill="#181818", spacing=body_spacing)


def _draw_scene_style_closer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    scene: Scene,
    scene_index: int,
    scene_total: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ScaledDraw(glow)
    glow_draw.ellipse((54, 860, 454, 1260), fill=_hex_to_rgba(light, 96))
    glow_draw.ellipse((746, 548, 1088, 890), fill=_hex_to_rgba(accent, 92))
    glow = glow.filter(glow_draw.blur(32))
    image.alpha_composite(glow)

    _draw_shadowed_round_box(image, (78, 620, 1008, 1668), 74, (255, 255, 255, 236), 124)
    _draw_label(draw, (118, 666, 436, 752), "LAST SLIDE", fonts["scene_tag"], _pill_fill(accent), "white")
    _draw_label(draw, (694, 666, 962, 752), "COMMENT & SHARE", fonts["scene_tag"], _hex_to_rgba(light, 224), background)

    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        742,
        190,
        60,
        bold=True,
        spacing=10,
        min_size=42,
        min_spacing=6,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        742,
        186,
        46,
        spacing=18,
        min_size=30,
        min_spacing=10,
    )
    content_top = _stack_top(842, 1324, [title_height, body_height], [56])
    draw.multiline_text((126, content_top), title, font=title_font, fill=background, spacing=title_spacing)
    draw.multiline_text((126, content_top + title_height + 56), body, font=body_font, fill="#181818", spacing=body_spacing)

    comment_text, comment_font, comment_spacing, _, comment_height = _fit_text_block(
        draw,
        "合ってたらコメントで教えてね",
        728,
        48,
        38,
        bold=True,
        spacing=6,
        min_size=24,
        min_spacing=2,
    )
    comment_box = (126, 1370, 962, 1370 + max(118, comment_height + 54))
    draw.rounded_rectangle(comment_box, radius=36, fill=_hex_to_rgba(light, 230))
    comment_y = comment_box[1] + max((comment_box[3] - comment_box[1] - comment_height) // 2, 0) - 2
    draw.multiline_text((174, comment_y), comment_text, font=comment_font, fill=background, spacing=comment_spacing)
    share_text, share_font, share_spacing, _, share_height = _fit_text_block(
        draw,
        "友だちに共有して答え合わせしてみて",
        618,
        48,
        30,
        bold=True,
        spacing=6,
        min_size=22,
        min_spacing=2,
    )
    share_box = (164, comment_box[3] + 38, 926, comment_box[3] + 38 + max(102, share_height + 42))
    draw.rounded_rectangle(share_box, radius=36, fill=_pill_fill(accent, 214))
    share_y = share_box[1] + max((share_box[3] - share_box[1] - share_height) // 2, 0) - 2
    draw.multiline_text((232, share_y), share_text, font=share_font, fill="white", spacing=share_spacing)


def _draw_pulse_thumbnail_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    card = PULSE_THUMBNAIL_CARD
    _draw_luxury_round_box(image, card, 64, (248, 255, 250, 247), accent, light, 148)
    draw = ScaledDraw(image)

    label_y = card[1] + 42
    _draw_label(draw, (112, label_y, 432, label_y + 78), f"{content_package.mbti_type} / {content_package.archetype_name}", fonts["scene_tag"], _pill_fill(accent), "white")
    _draw_label(
        draw,
        (676, label_y, 958, label_y + 78),
        f"COVER {content_package.series_post_number}/{content_package.series_total_posts}",
        fonts["detail"],
        _hex_to_rgba(light),
        background,
    )

    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        content_package.title,
        800,
        450,
        90,
        bold=True,
        spacing=14,
        min_size=54,
        min_spacing=6,
    )
    title_area_top = card[1] + 172
    title_area_bottom = card[3] - 142
    title_y = title_area_top + max((title_area_bottom - title_area_top - title_height) // 2, 0)
    draw.multiline_text(
        (120, title_y + 6),
        title,
        font=title_font,
        fill=_hex_to_rgba(accent, 82),
        spacing=title_spacing,
    )
    draw.multiline_text((116, title_y), title, font=title_font, fill=background, spacing=title_spacing)
    _draw_luxury_divider(draw, 126, 954, card[3] - 92, accent, light)


def _draw_pulse_scene_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    content_index = _content_scene_index(content_package, scene_index)
    scene_total = _content_scene_total(content_package)
    card = PULSE_MAIN_CARD
    _draw_shadowed_round_box(image, card, 58, (248, 255, 250, 255), 112)

    label_y = card[1] + 40
    _draw_label(draw, (112, label_y, 334, label_y + 72), f"POINT {content_index + 1}", fonts["scene_tag"], _pill_fill(accent), "white")
    _draw_label(draw, (374, label_y, 646, label_y + 72), f"{content_package.mbti_type} / {content_package.archetype_name}", fonts["detail"], _hex_to_rgba(light), background)
    _draw_label(draw, (742, label_y, 958, label_y + 72), f"{content_index + 1:02d} / {scene_total}", fonts["scene_tag"], _hex_to_rgba(light), background)

    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        800,
        170,
        58,
        bold=True,
        spacing=10,
        min_size=38,
        min_spacing=5,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        768,
        352,
        48,
        spacing=16,
        min_size=30,
        min_spacing=8,
    )

    title_y = card[1] + 150
    draw.multiline_text((116, title_y), title, font=title_font, fill=background, spacing=title_spacing)

    body_box = (112, max(title_y + title_height + 48, 1058), 968, 1518)
    draw.rounded_rectangle(body_box, radius=40, fill=(255, 255, 255, 255))
    draw.rounded_rectangle((144, body_box[1] + 46, 264, body_box[1] + 56), radius=5, fill=_hex_to_rgba(accent))
    body_y = body_box[1] + 116 + max((body_box[3] - body_box[1] - 156 - body_height) // 2, 0)
    draw.multiline_text((150, body_y), body, font=body_font, fill="#181818", spacing=body_spacing)

    draw.rounded_rectangle((112, 1548, 968, 1588), radius=18, fill=_hex_to_rgba(light))


def _draw_pulse_closer_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    scene: Scene,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    card = PULSE_CLOSER_CARD
    _draw_shadowed_round_box(image, card, 64, (248, 255, 250, 255), 118)
    _draw_label(draw, (112, 766, 414, 838), "LAST SLIDE", fonts["scene_tag"], _pill_fill(accent), "white")
    _draw_label(draw, (626, 766, 958, 838), "COMMENT & SHARE", fonts["scene_tag"], _hex_to_rgba(light), background)

    title, title_font, title_spacing, _, title_height = _fit_text_block(
        draw,
        scene.title,
        780,
        170,
        58,
        bold=True,
        spacing=10,
        min_size=40,
        min_spacing=6,
    )
    body, body_font, body_spacing, _, body_height = _fit_text_block(
        draw,
        scene.body,
        780,
        210,
        42,
        spacing=14,
        min_size=28,
        min_spacing=8,
    )
    draw.multiline_text((126, 906), title, font=title_font, fill=background, spacing=title_spacing)
    draw.multiline_text((126, 906 + title_height + 46), body, font=body_font, fill="#181818", spacing=body_spacing)

    comment_text, comment_font, comment_spacing, _, comment_height = _fit_text_block(
        draw,
        "合ってたらコメントで教えてね",
        724,
        52,
        36,
        bold=True,
        spacing=6,
        min_size=26,
        min_spacing=2,
    )
    comment_box = (126, 1306, 954, 1416)
    draw.rounded_rectangle(comment_box, radius=34, fill=_hex_to_rgba(light))
    comment_y = comment_box[1] + max((comment_box[3] - comment_box[1] - comment_height) // 2, 0) - 2
    draw.multiline_text((172, comment_y), comment_text, font=comment_font, fill=background, spacing=comment_spacing)

    share_text, share_font, share_spacing, _, share_height = _fit_text_block(
        draw,
        "友だちにも共有して答え合わせしてみて",
        640,
        52,
        30,
        bold=True,
        spacing=6,
        min_size=24,
        min_spacing=2,
    )
    share_box = (164, 1454, 916, 1558)
    draw.rounded_rectangle(share_box, radius=34, fill=_pill_fill(accent))
    share_y = share_box[1] + max((share_box[3] - share_box[1] - share_height) // 2, 0) - 2
    draw.multiline_text((218, share_y), share_text, font=share_font, fill="white", spacing=share_spacing)


def _draw_pulse_text_overlay(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    if _is_thumbnail_scene(content_package, scene, scene_index):
        _draw_pulse_thumbnail_overlay(image, draw, content_package, background, accent, light, fonts)
        return
    if _is_closer_scene(content_package, scene, scene_index):
        _draw_pulse_closer_overlay(image, draw, scene, background, accent, light, fonts)
        return
    _draw_pulse_scene_overlay(image, draw, content_package, scene, scene_index, background, accent, light, fonts)


def _draw_scene_content(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    scene: Scene,
    scene_index: int,
    content_package: ContentPackage,
    background: str,
    accent: str,
    light: str,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    if _is_closer_scene(content_package, scene, scene_index):
        _draw_scene_style_closer(
            image,
            draw,
            scene,
            _content_scene_total(content_package),
            _content_scene_total(content_package),
            background,
            accent,
            light,
            fonts,
        )
        return

    content_scene_index = _content_scene_index(content_package, scene_index)
    scene_total = _content_scene_total(content_package)
    style_key = _scene_style_key(content_package, scene, scene_index)
    if style_key == "spotlight":
        _draw_scene_style_spotlight(
            image,
            draw,
            content_package,
            scene,
            content_scene_index,
            scene_total,
            background,
            accent,
            light,
            fonts,
        )
        return
    if style_key == "bottom_board":
        _draw_scene_style_bottom_board(
            image,
            draw,
            content_package,
            scene,
            content_scene_index,
            scene_total,
            background,
            accent,
            light,
            fonts,
        )
        return
    if style_key == "chat":
        _draw_scene_style_chat(image, draw, content_package, scene, content_scene_index, background, accent, light, fonts)
        return
    if style_key == "slam":
        _draw_scene_style_slam(image, draw, content_package, scene, content_scene_index, background, accent, light, fonts)
        return
    _draw_scene_style_wrapup(
        image,
        draw,
        content_package,
        scene,
        content_scene_index,
        scene_total,
        background,
        accent,
        light,
        fonts,
    )


def _draw_spark(draw: ImageDraw.ImageDraw, center: tuple[int, int], size: int, color: tuple[int, int, int, int]) -> None:
    x, y = center
    draw.line((x - size, y, x + size, y), fill=color, width=max(2, size // 4))
    draw.line((x, y - size, x, y + size), fill=color, width=max(2, size // 4))
    draw.line((x - size // 2, y - size // 2, x + size // 2, y + size // 2), fill=color, width=max(2, size // 5))
    draw.line((x - size // 2, y + size // 2, x + size // 2, y - size // 2), fill=color, width=max(2, size // 5))


# The same double frame, four corner brackets, four jewels and bottom divider
# used to land on every slide of every post, which is a large part of why the
# output read as one template. These are the treatments a post can draw.
CHROME_TREATMENTS = ("frame_full", "frame_hairline", "corners_only", "rule_top", "bare")


def _chrome_plan(seed: int) -> dict[str, object]:
    """Pick the chrome for a post. Salted so it does not track the layout."""
    return {
        "treatment": CHROME_TREATMENTS[_seed_choice(seed, "chrome", len(CHROME_TREATMENTS))],
        "speckles": _seed_choice(seed, "speckles", 3) > 0,
        "divider": _seed_choice(seed, "divider", 2) == 0,
        "jewels": _seed_choice(seed, "jewels", 3) > 0,
    }


def _draw_chrome_speckles(draw, width: int, height: int, seed: int) -> None:
    for index in range(84):
        x = 54 + ((seed >> (index % 24)) + index * 149) % max(width - 108, 1)
        y = 74 + ((seed >> ((index + 7) % 24)) + index * 233) % max(height - 148, 1)
        radius = 1 + index % 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, 15 + (index % 3) * 5))


def _draw_chrome_corners(draw, width: int, height: int, accent: str, light: str, jewels: bool) -> None:
    corner = 116
    for x_sign, y_sign in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x = 56 if x_sign == 1 else width - 56
        y = 56 if y_sign == 1 else height - 56
        draw.line((x, y, x + x_sign * corner, y), fill=_hex_to_rgba(accent, 108), width=4)
        draw.line((x, y, x, y + y_sign * corner), fill=_hex_to_rgba(accent, 108), width=4)
        if not jewels:
            continue
        jewel_x = x + x_sign * 18
        jewel_y = y + y_sign * 18
        draw.polygon(
            ((jewel_x, jewel_y - 7), (jewel_x + 7, jewel_y), (jewel_x, jewel_y + 7), (jewel_x - 7, jewel_y)),
            fill=_hex_to_rgba(light, 150),
        )


def _draw_luxury_canvas_details(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    accent: str,
    light: str,
    seed: int,
) -> None:
    """Frame and texture the canvas, in one of five treatments."""
    plan = _chrome_plan(seed)
    treatment = plan["treatment"]
    outer = (24, 24, width - 24, height - 24)
    inner = (39, 39, width - 39, height - 39)

    if treatment == "frame_full":
        draw.rounded_rectangle(outer, radius=58, outline=_hex_to_rgba(light, 78), width=3)
        draw.rounded_rectangle(inner, radius=48, outline=(255, 255, 255, 26), width=2)
        _draw_chrome_corners(draw, width, height, accent, light, plan["jewels"])
    elif treatment == "frame_hairline":
        draw.rounded_rectangle(inner, radius=48, outline=_hex_to_rgba(light, 64), width=2)
    elif treatment == "corners_only":
        _draw_chrome_corners(draw, width, height, accent, light, plan["jewels"])
    elif treatment == "rule_top":
        draw.rounded_rectangle((94, 188, width - 94, 194), radius=3, fill=_hex_to_rgba(accent, 120))

    if plan["speckles"]:
        _draw_chrome_speckles(draw, width, height, seed)
    if plan["divider"] and treatment != "bare":
        _draw_luxury_divider(draw, 94, width - 94, height - 112, accent, light)


# --- editorial motif -------------------------------------------------------
# Ported from scripts/create_editorial_*.py, which produced markedly better
# looking slides than the illustrated path but were hand-edited one-offs with
# their own naive character-by-character wrapper. The copy here goes through
# _fit_text_block, so it gets the kinsoku handling in typeset.py; the scripts
# split 雑にしない across two lines.
EDITORIAL_GOLD = (226, 196, 134)
EDITORIAL_CREAM = (245, 230, 196, 255)
EDITORIAL_GLASS = (8, 10, 13, 196)
EDITORIAL_PHOTO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@lru_cache(maxsize=8)
def _editorial_photos(photos_dir: str) -> tuple[Path, ...]:
    root = Path(photos_dir)
    if not root.is_dir():
        return ()
    return tuple(sorted(p for p in root.iterdir() if p.suffix.lower() in EDITORIAL_PHOTO_SUFFIXES))


def _editorial_photo_plan(photo_count: int, seed: int, slide_count: int) -> list[dict[str, object]]:
    """One photo per slide, plus a treatment that disguises reuse.

    Written to work with any number of photos. With fewer photos than slides
    the same picture has to come back, so each appearance gets a different
    crop and zoom, and the same one never lands on two slides in a row.
    """
    if photo_count <= 0:
        return []
    order = [(_seed_choice(seed, "photo", photo_count) + index) % photo_count for index in range(slide_count)]
    if photo_count > 1:
        for index in range(1, len(order)):
            if order[index] == order[index - 1]:
                order[index] = (order[index] + 1) % photo_count
    return [
        {
            "index": photo_index,
            "centering": (0.5 + (_seed_choice(seed, f"crop{position}", 5) - 2) * 0.08, 0.5),
            "zoom": 1.0 + _seed_choice(seed, f"zoom{position}", 4) * 0.06,
            "align": "right" if position % 2 else "left",
        }
        for position, photo_index in enumerate(order)
    ]


def _fit_cover(source: Image.Image, size: tuple[int, int], centering: tuple[float, float], zoom: float) -> Image.Image:
    target_width, target_height = size
    scaled = (round(target_width * zoom), round(target_height * zoom))
    covered = ImageOps.fit(source, scaled, method=Image.Resampling.LANCZOS, centering=centering)
    left = (scaled[0] - target_width) // 2
    top = (scaled[1] - target_height) // 2
    return covered.crop((left, top, left + target_width, top + target_height))


def _editorial_scrim(canvas: ScaledDraw, align: str) -> Image.Image:
    """Darken the frame so cream text holds against any photograph.

    Built from one-pixel strips rather than a per-row draw.line loop; at render
    scale that loop ran 3840 times per slide.
    """
    width, height = canvas.image.size
    vertical = Image.new("L", (1, height))
    vertical.putdata([
        min(int(40 + 205 * max(0.0, (y / height - 0.18) / 0.82) ** 1.55), 230)
        for y in range(height)
    ])
    horizontal = Image.new("L", (width, 1))
    if align == "right":
        horizontal.putdata([int(130 * max(0.0, 1 - x / width) ** 1.8) for x in range(width)])
    else:
        horizontal.putdata([int(118 * max(0.0, x / width) ** 1.8) for x in range(width)])

    alpha = ImageChops.lighter(
        vertical.resize((width, height), Image.Resampling.BILINEAR),
        horizontal.resize((width, height), Image.Resampling.BILINEAR),
    )
    scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    scrim.putalpha(alpha)
    return scrim


def _draw_editorial_pill(canvas: ScaledDraw, xy: tuple[int, int], text: str, font) -> None:
    x, y = xy
    box = _measure_draw().textbbox((0, 0), text, font=font)
    width = box[2] - box[0] + 48
    height = box[3] - box[1] + 26
    canvas.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=height // 2,
        fill=(14, 18, 22, 178),
        outline=(229, 202, 150, 210),
        width=2,
    )
    canvas.text((x + 24, y + 11), text, font=font, fill=EDITORIAL_CREAM)


def _draw_editorial_shadow_text(canvas: ScaledDraw, xy: tuple[int, int], text: str, font, fill, spacing: int) -> None:
    x, y = xy
    canvas.multiline_text((x + 4, y + 6), text, font=font, fill=(0, 0, 0, 150), spacing=spacing)
    canvas.multiline_text((x, y), text, font=font, fill=fill, spacing=spacing)


def _build_background_layer(content_package: ContentPackage, config: AppConfig) -> Image.Image:
    width = config.video_width
    height = config.video_height
    device = (width * RENDER_SCALE, height * RENDER_SCALE)
    palette = _palette(content_package)
    background, accent, light = palette.background, palette.accent, palette.light
    image = _make_gradient(device[0], device[1], background, accent)

    blur_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    blur_draw = ScaledDraw(blur_layer)
    blur_draw.ellipse((-120, 1280, 520, 1900), fill=_hex_to_rgba(light, 80))
    blur_draw.ellipse((670, 80, 1220, 780), fill=_hex_to_rgba(accent, 85))
    blur_draw.rounded_rectangle((560, 420, 1130, 1600), radius=110, fill=(255, 255, 255, 20))
    blur_layer = blur_layer.filter(blur_draw.blur(48))
    image.alpha_composite(blur_layer)

    draw = ScaledDraw(image)
    motif = _motif_key(content_package)
    if motif == "chat":
        for y in range(240, height - 240, 180):
            draw.rounded_rectangle((84, y, 454, y + 84), radius=28, fill=_hex_to_rgba(light, 26))
            draw.rounded_rectangle((592, y + 72, 980, y + 172), radius=34, fill=_hex_to_rgba(accent, 22))
    elif motif == "grid":
        for x in range(48, width, 182):
            for y in range(160, height, 248):
                right = min(x + 128, width - 40)
                bottom = min(y + 128, height - 40)
                if right <= x or bottom <= y:
                    continue
                draw.rounded_rectangle((x, y, right, bottom), radius=30, outline=_hex_to_rgba(light, 40), width=3)
    elif motif == "pulse":
        center_x, center_y = 228, 1320
        for radius in (120, 210, 300, 390):
            draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), outline=_hex_to_rgba(light, 36), width=4)
        draw.ellipse((740, 220, 1040, 520), fill=_hex_to_rgba(accent, 24))
    elif motif == "orbit":
        for radius in (170, 280, 390):
            draw.ellipse((680 - radius, 420 - radius, 680 + radius, 420 + radius), outline=_hex_to_rgba(light, 34), width=3)
        draw.ellipse((110, 1360, 450, 1700), fill=_hex_to_rgba(accent, 22))
    else:
        # A light diagonal texture. At 180px spacing, plus a second heavier pass
        # across the lower half, this read as scratches over the artwork rather
        # than as a background, so keep it wide and faint.
        for offset in range(-height, width, 420):
            draw.line(
                [(offset, 0), (offset + height, height)],
                fill=(255, 255, 255, 10),
                width=2,
            )

    luxury_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    luxury_draw = ScaledDraw(luxury_layer)
    _draw_luxury_canvas_details(
        luxury_draw,
        width,
        height,
        accent,
        light,
        _visual_seed(content_package, include_mbti=False),
    )
    image.alpha_composite(luxury_layer)

    return image


def _build_text_layer(
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    config: AppConfig,
) -> Image.Image:
    width = config.video_width
    height = config.video_height
    device = (width * RENDER_SCALE, height * RENDER_SCALE)
    palette = _palette(content_package)
    background, accent, light = palette.background, palette.accent, palette.light
    image = Image.new("RGBA", device, (0, 0, 0, 0))
    draw = ScaledDraw(image)

    # Every title and body font is resolved inside _fit_text_block, which picks
    # a size to fit its box. Only these three are drawn at a fixed size.
    fonts = {
        "scene_tag": _load_font(32, bold=True),
        "detail": _load_font(30, bold=True),
        "count": _load_font(40, bold=True),
    }

    if _is_pulse_layout(content_package):
        _draw_pulse_text_overlay(image, draw, content_package, scene, scene_index, background, accent, light, fonts)
        return image

    if _is_thumbnail_scene(content_package, scene, scene_index):
        _draw_thumbnail_overlay(image, draw, content_package, background, accent, light, fonts)
        return image

    _draw_content_header(draw, content_package, background, accent, light, fonts)
    _draw_scene_content(image, draw, scene, scene_index, content_package, background, accent, light, fonts)

    return image


def _build_editorial_text_layer(
    content_package: ContentPackage,
    scene: Scene,
    scene_index: int,
    config: AppConfig,
    align: str,
) -> Image.Image:
    width = config.video_width
    height = config.video_height
    device = (width * RENDER_SCALE, height * RENDER_SCALE)
    image = Image.new("RGBA", device, (0, 0, 0, 0))
    canvas = ScaledDraw(image)
    canvas.image.alpha_composite(_editorial_scrim(canvas, align))

    is_thumbnail = _is_thumbnail_scene(content_package, scene, scene_index)
    content_index = _content_scene_index(content_package, scene_index)
    total = _content_scene_total(content_package)
    pill_font = _load_font(32, bold=True)

    if is_thumbnail:
        eyebrow = f"{content_package.mbti_type} / {content_package.archetype_name}"
    elif _is_closer_scene(content_package, scene, scene_index):
        eyebrow = f"{content_package.mbti_type} / LAST"
    else:
        eyebrow = f"{content_package.mbti_type} / POINT {content_index + 1:02d}"
    _draw_editorial_pill(canvas, (96, 96), eyebrow, pill_font)

    title_text, title_font, title_spacing, _, title_height = _fit_text_block(
        canvas,
        scene.title,
        888,
        330 if is_thumbnail else 250,
        104 if is_thumbnail else 76,
        bold=True,
        spacing=18,
        min_size=52 if is_thumbnail else 44,
        min_spacing=10,
    )
    body_text, body_font, body_spacing, _, body_height = _fit_text_block(
        canvas,
        scene.body,
        832,
        224,
        46,
        spacing=16,
        min_size=32,
        min_spacing=8,
    )

    # Stacked from the bottom so the footer rule always clears the panel. Laying
    # the panel out downwards from a fixed top ran it over the footer whenever
    # the body needed a fifth line.
    footer_y = height - 104
    panel_bottom = footer_y - 52
    panel_top = panel_bottom - body_height - 84
    panel = (78, panel_top, width - 78, panel_bottom)
    canvas.rounded_rectangle(panel, radius=32, fill=EDITORIAL_GLASS, outline=(255, 255, 255, 46), width=2)
    canvas.rounded_rectangle((panel[0], panel[1], panel[2], panel[1] + 6), radius=3, fill=(*EDITORIAL_GOLD, 210))
    canvas.multiline_text((panel[0] + 40, panel[1] + 40), body_text, font=body_font, fill=EDITORIAL_CREAM, spacing=body_spacing)

    title_y = panel_top - title_height - 44
    _draw_editorial_shadow_text(canvas, (96, title_y), title_text, title_font, (255, 255, 255, 255), title_spacing)

    footer = f"{content_index + 1:02d} / {total:02d}" if not is_thumbnail else "SWIPE →"
    footer_width = _measure_draw().textbbox((0, 0), footer, font=pill_font)[2]
    canvas.line((96, footer_y + 16, width - 132 - footer_width, footer_y + 16), fill=(*EDITORIAL_GOLD, 150), width=2)
    canvas.text((width - 96 - footer_width, footer_y), footer, font=pill_font, fill=EDITORIAL_CREAM)
    return image


def _build_character_layer(
    content_package: ContentPackage,
    config: AppConfig,
    scene_index: int = 0,
) -> Image.Image:
    width = config.video_width
    height = config.video_height
    device = (width * RENDER_SCALE, height * RENDER_SCALE)
    palette = _palette(content_package)
    accent, light = palette.accent, palette.light
    image = Image.new("RGBA", device, (0, 0, 0, 0))
    draw = ScaledDraw(image)

    box = _scene_character_box(content_package, scene_index)
    glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ScaledDraw(glow_layer)
    glow_draw.ellipse((box[0] - 40, box[1] + 30, box[2] + 50, box[3] - 40), fill=_hex_to_rgba(accent, 120))
    glow_draw.ellipse((box[0] + 20, box[1] - 90, box[2] - 20, box[1] + 380), fill=_hex_to_rgba(light, 85))
    glow_layer = glow_layer.filter(glow_draw.blur(52))
    image.alpha_composite(glow_layer)

    _draw_topic_illustration_stage(image, box, accent, light, content_package)

    source_path = _resolve_illustration_path(config, content_package.mbti_type)
    if source_path is None:
        raise FileNotFoundError(
            f"Provided MBTI material is required for {content_package.mbti_type}; "
            f"place it in {config.official_images_dir} or {config.assets_dir}"
        )

    with Image.open(source_path) as opened_source:
        source = opened_source.convert("RGBA")
        alpha = source.getchannel("A")
        alpha_min, alpha_max = alpha.getextrema()
        has_transparency = alpha_min < alpha_max

    topic_variant = _visual_seed(content_package, include_mbti=False) % 8
    is_thumbnail = scene_index == 0
    composition_variant = topic_variant if is_thumbnail else (topic_variant + scene_index * 3) % 8
    frame_width = box[2] - box[0]
    frame_height = box[3] - box[1]
    # box and the frame drawing below are logical, but the source art, the
    # masks and every paste offset are real pixels. Keep the two apart.
    dev_box = tuple(draw.px(value) for value in box)
    dev_width = dev_box[2] - dev_box[0]
    dev_height = dev_box[3] - dev_box[1]

    if has_transparency:
        alpha_bbox = source.getchannel("A").getbbox()
        if alpha_bbox is not None:
            source = source.crop(alpha_bbox)
        thumbnail_scales = (0.9, 0.94, 0.92, 0.96, 0.91, 0.95, 0.93, 0.97)
        content_scales = (0.76, 0.86, 1.0, 0.82, 0.94, 0.78, 0.9, 0.84)
        scale = thumbnail_scales[composition_variant] if is_thumbnail else content_scales[composition_variant]
        max_size = (max(int(dev_width * scale), 1), max(int(dev_height * scale), 1))
        source.thumbnail(max_size, Image.Resampling.LANCZOS)
        # Not mirrored. Some of the provided art carries lettering - the ESTP
        # bag reads SPORT - and a flip renders it backwards, which looks like a
        # mistake rather than a variation. Scale, rotation and offset below
        # still vary the composition.
        thumbnail_angles = (-2, 2, 0, 3, -1, 2, -3, 1)
        content_angles = (-7, 6, -4, 8, -6, 5, -8, 4)
        angle = thumbnail_angles[composition_variant] if is_thumbnail else content_angles[composition_variant]
        source = source.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        shadow = Image.new("RGBA", source.size, (0, 0, 0, 0))
        shadow_alpha = source.getchannel("A").filter(draw.blur(18))
        shadow.paste((0, 0, 0, 130), (0, 0), shadow_alpha)
        thumbnail_x_bias = (-0.04, 0.05, -0.02, 0.04, -0.03, 0.02, 0.04, -0.01)
        thumbnail_y_bias = (0.02, -0.01, 0.04, 0.0, 0.05, -0.02, 0.03, 0.01)
        content_x_bias = (-0.16, 0.15, -0.1, 0.13, -0.14, 0.1, 0.16, -0.08)
        content_y_bias = (0.1, -0.05, 0.12, -0.04, 0.14, -0.08, 0.08, 0.04)
        x_bias = thumbnail_x_bias[composition_variant] if is_thumbnail else content_x_bias[composition_variant]
        y_bias = thumbnail_y_bias[composition_variant] if is_thumbnail else content_y_bias[composition_variant]
        x = dev_box[0] + (dev_width - source.width) // 2 + int(dev_width * x_bias)
        y = dev_box[1] + (dev_height - source.height) // 2 + int(dev_height * y_bias)
        image.alpha_composite(shadow, (x + draw.px(16), y + draw.px(20)))
        image.alpha_composite(source, (x, y))
    else:
        centering_x = (0.34, 0.66, 0.5, 0.42, 0.58, 0.28, 0.72, 0.5)[composition_variant]
        centering_y = (0.5, 0.42, 0.58, 0.36, 0.64, 0.48, 0.54, 0.4)[composition_variant]
        portrait = ImageOps.fit(
            source.convert("RGB"),
            (dev_width - draw.px(32), dev_height - draw.px(32)),
            method=Image.Resampling.LANCZOS,
            centering=(centering_x, centering_y),
        )
        # Not mirrored. Some of the provided art carries lettering - the ESTP
        # bag reads SPORT - and a flip renders it backwards, which looks like a
        # mistake rather than a variation. Scale, rotation and offset below
        # still vary the composition.
        mask = Image.new("L", portrait.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        frame_style = (topic_variant + scene_index) % 3
        if frame_style == 0:
            mask_draw.rounded_rectangle((0, 0, portrait.width, portrait.height), radius=44, fill=255)
        elif frame_style == 1:
            mask_draw.ellipse((0, 0, portrait.width, portrait.height), fill=255)
        else:
            mask_draw.polygon(
                ((portrait.width // 2, 0), (portrait.width, portrait.height // 5), (portrait.width, portrait.height), (0, portrait.height), (0, portrait.height // 5)),
                fill=255,
            )

        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ScaledDraw(shadow_layer)
        shadow_draw.rounded_rectangle((box[0] + 14, box[1] + 18, box[2] + 14, box[3] + 18), radius=56, fill=(0, 0, 0, 118))
        shadow_layer = shadow_layer.filter(draw.blur(24))
        image.alpha_composite(shadow_layer)

        if frame_style == 0:
            draw.rounded_rectangle(box, radius=56, fill=(255, 255, 255, 235), outline=light, width=6)
        elif frame_style == 1:
            draw.ellipse(box, fill=(255, 255, 255, 235), outline=light, width=6)
        else:
            draw.polygon(((box[0] + frame_width // 2, box[1]), (box[2], box[1] + frame_height // 5), (box[2], box[3]), (box[0], box[3]), (box[0], box[1] + frame_height // 5)), fill=(255, 255, 255, 235), outline=light)
        image.paste(portrait.convert("RGBA"), (dev_box[0] + draw.px(16), dev_box[1] + draw.px(16)), mask)

    if is_thumbnail:
        badge_font = _load_font(42, bold=True)
        badge_box = (box[0] + 60, box[3] - 70, box[2] - 50, box[3] + 30)
        # The cover card is drawn in the text layer, which lands on top of this
        # one, so a badge that overlaps it gets clipped by it. Only the grid
        # motif reaches far enough right for that to happen.
        badge_box = _shifted_clear_of(badge_box, _thumbnail_layout(content_package)["card"])
        draw.rounded_rectangle(badge_box, radius=36, fill=(255, 255, 255, 230))
        badge_width = _measure_draw().textbbox((0, 0), content_package.mbti_type, font=badge_font)[2]
        badge_x = badge_box[0] + ((badge_box[2] - badge_box[0]) - badge_width) // 2
        draw.text((badge_x, badge_box[1] + 22), content_package.mbti_type, font=badge_font, fill=accent)
    else:
        marker_radius = 20 + (scene_index % 3) * 6
        marker_x = box[2] - 16
        marker_y = box[1] + 54
        draw.ellipse(
            (marker_x - marker_radius, marker_y - marker_radius, marker_x + marker_radius, marker_y + marker_radius),
            fill=_hex_to_rgba(light, 220),
            outline=_hex_to_rgba(accent, 240),
            width=5,
        )

    return image


def _build_accent_layer(content_package: ContentPackage, config: AppConfig) -> Image.Image:
    width = config.video_width
    height = config.video_height
    device = (width * RENDER_SCALE, height * RENDER_SCALE)
    palette = _palette(content_package)
    accent, light = palette.accent, palette.light
    image = Image.new("RGBA", device, (0, 0, 0, 0))
    draw = ScaledDraw(image)

    motif = _motif_key(content_package)
    if motif == "chat":
        draw.rounded_rectangle((786, 164, 1018, 252), radius=30, fill=_hex_to_rgba(light, 70))
        draw.rounded_rectangle((724, 1334, 1020, 1436), radius=34, fill=_hex_to_rgba(accent, 62))
        draw.ellipse((890, 300, 952, 362), fill=_hex_to_rgba(light, 120))
    elif motif == "grid":
        for x in (742, 844, 946):
            draw.rounded_rectangle((x, 178, x + 70, 248), radius=18, fill=_hex_to_rgba(light, 66))
        draw.rounded_rectangle((734, 1398, 1008, 1432), radius=14, fill=_hex_to_rgba(accent, 78))
    elif motif == "pulse":
        for radius in (54, 94, 134):
            draw.ellipse((852 - radius, 286 - radius, 852 + radius, 286 + radius), outline=_hex_to_rgba(light, 54), width=4)
        draw.rounded_rectangle((768, 1382, 800, 1762), radius=16, fill=_hex_to_rgba(accent, 58))
    elif motif == "orbit":
        draw.ellipse((742, 132, 1028, 418), outline=_hex_to_rgba(light, 58), width=4)
        draw.ellipse((806, 196, 964, 354), outline=_hex_to_rgba(accent, 72), width=4)
        draw.ellipse((822, 1330, 918, 1426), fill=_hex_to_rgba(light, 96))
    else:
        draw.rounded_rectangle((760, 180, 790, 980), radius=18, fill=_hex_to_rgba(light, 58))
        draw.rounded_rectangle((824, 148, 846, 920), radius=12, fill=_hex_to_rgba(accent, 70))
        draw.ellipse((844, 284, 904, 344), fill=_hex_to_rgba(light, 120))
        draw.ellipse((882, 330, 918, 366), fill=_hex_to_rgba(accent, 95))
        draw.ellipse((820, 1210, 874, 1264), fill=_hex_to_rgba(light, 88))
        draw.polygon([(860, 90), (990, 90), (880, 340), (760, 340)], fill=_hex_to_rgba(accent, 28))
        draw.polygon([(790, 1420), (980, 1420), (930, 1760), (740, 1760)], fill=_hex_to_rgba(light, 24))

    return image


def _build_scene_accent_layer(
    content_package: ContentPackage,
    scene_index: int,
    config: AppConfig,
) -> Image.Image:
    width = config.video_width
    height = config.video_height
    device = (width * RENDER_SCALE, height * RENDER_SCALE)
    palette = _palette(content_package)
    background, accent, light = palette.background, palette.accent, palette.light
    image = Image.new("RGBA", device, (0, 0, 0, 0))
    draw = ScaledDraw(image)
    scene = content_package.scenes[scene_index]
    style_key = _scene_style_key(content_package, scene, scene_index)

    if style_key == "spotlight":
        draw.rounded_rectangle((732, 248, 770, 1118), radius=18, fill=_hex_to_rgba(light, 62))
        draw.rounded_rectangle((790, 210, 816, 980), radius=12, fill=_hex_to_rgba(accent, 92))
        draw.ellipse((820, 312, 930, 422), fill=_hex_to_rgba(light, 120))
        draw.polygon([(874, 114), (1018, 114), (888, 384), (744, 384)], fill=_hex_to_rgba(accent, 30))
        _draw_spark(draw, (900, 1490), 42, _hex_to_rgba(light, 210))
    elif style_key == "bottom_board":
        for y in (252, 324, 396):
            draw.rounded_rectangle((676, y, 1010, y + 26), radius=12, fill=_hex_to_rgba(light, 72))
        draw.rounded_rectangle((120, 972, 1000, 1004), radius=12, fill=_hex_to_rgba(accent, 86))
        draw.rounded_rectangle((120, 1760, 952, 1790), radius=12, fill=_hex_to_rgba(light, 58))
    elif style_key == "chat":
        draw.rounded_rectangle((82, 580, 180, 610), radius=10, fill=_hex_to_rgba(light, 110))
        draw.rounded_rectangle((908, 888, 1006, 918), radius=10, fill=_hex_to_rgba(accent, 110))
        for point in ((840, 690), (906, 756), (968, 818), (272, 1464)):
            _draw_spark(draw, point, 24, _hex_to_rgba(light, 180))
    elif style_key == "slam":
        draw.polygon([(742, 242), (1052, 242), (948, 722), (638, 722)], fill=_hex_to_rgba(accent, 24))
        for radius in (150, 228, 306):
            draw.ellipse((760 - radius, 1260 - radius, 760 + radius, 1260 + radius), outline=_hex_to_rgba(light, 32), width=4)
        draw.rounded_rectangle((84, 1112, 818, 1140), radius=14, fill=_hex_to_rgba(light, 70))
    else:
        draw.rounded_rectangle((94, 644, 986, 680), radius=14, fill=_hex_to_rgba(accent, 62))
        draw.rounded_rectangle((94, 1586, 986, 1616), radius=14, fill=_hex_to_rgba(light, 68))
        draw.ellipse((858, 362, 978, 482), fill=_hex_to_rgba(light, 98))
        draw.ellipse((108, 1490, 212, 1594), fill=_hex_to_rgba(accent, 86))

    # The glow belongs under the shapes. Compositing the blur back onto the
    # image it was made from drew every accent twice and squared its alpha,
    # which is why these shapes read heavier than the values here suggest.
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow.alpha_composite(image.filter(draw.blur(14)))
    glow.alpha_composite(image)
    image = glow
    base_overlay = _build_accent_layer(content_package, config)
    base_overlay.alpha_composite(image)
    return base_overlay


def _compose_scene(
    layers: list[Image.Image],
    size: tuple[int, int],
    destination: Path,
    base: Image.Image | None = None,
) -> Path:
    """Flatten the scene's layers onto the background and write the slide.

    The layers are composited at render scale and downsampled once, here.
    Resampling each layer separately would run the alpha edges through LANCZOS
    four times and can seam where two layers abut.
    """
    canvas = layers[0]
    for layer in layers[1:]:
        canvas.alpha_composite(layer)
    if canvas.size != size:
        canvas = canvas.resize(size, Image.Resampling.LANCZOS)
    if base is not None:
        # The editorial photographs are 941x1672, smaller than the canvas, so
        # fit_cover already enlarges them. Compositing them at render scale
        # would enlarge them 2.3x instead of 1.15x for no gain, so the photo
        # goes underneath after the overlay has come back down to size.
        composed = base.convert("RGBA")
        composed.alpha_composite(canvas)
        canvas = composed
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(destination)
    return destination


def _render_character_overlay(
    content_package: ContentPackage,
    config: AppConfig,
    destination: Path,
    scene_index: int = 0,
) -> Path:
    """Write the character layer on its own. Kept for tests and debugging."""
    image = _build_character_layer(content_package, config, scene_index=scene_index)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination


def _save_layer(image: Image.Image, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination


def generate_scene_assets(content_package: ContentPackage, config: AppConfig, slides_dir: Path) -> list[SceneRenderAssets]:
    if slides_dir.exists():
        shutil.rmtree(slides_dir)
    slides_dir.mkdir(parents=True, exist_ok=True)
    render_dir = slides_dir.parent / "_render"
    if render_dir.exists():
        try:
            shutil.rmtree(render_dir)
        except (PermissionError, OSError):
            # Handle Windows file locking issues by using onerror callback
            import stat
            def handle_remove_error(func, path, exc_info):
                import os
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
                    func(path)
                else:
                    raise
            try:
                shutil.rmtree(render_dir, onerror=handle_remove_error)
            except Exception:
                pass  # If removal fails completely, continue anyway
    shared_dir = render_dir / "_shared"
    if config.keep_render_layers:
        shared_dir.mkdir(parents=True, exist_ok=True)
    (slides_dir.parent / "visual_identity.json").write_text(
        json.dumps(_visual_identity(content_package), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # The layers only reach disk when someone asked to look at them. Writing
    # four PNGs per slide and deleting them again cost more than the slides.
    keep = config.keep_render_layers
    photos = _editorial_photos(str(config.editorial_photos_dir))
    available = ALL_MOTIFS if photos else ILLUSTRATED_MOTIFS
    editorial = _motif_key(content_package, available=available) == "editorial"
    photo_plan = (
        _editorial_photo_plan(len(photos), _visual_seed(content_package), len(content_package.scenes))
        if editorial
        else []
    )

    background_path = shared_dir / "background.png"
    background = None if editorial else _build_background_layer(content_package, config)
    if keep and background is not None:
        _save_layer(background, background_path)

    assets: list[SceneRenderAssets] = []
    for index, scene in enumerate(content_package.scenes):
        if editorial:
            entry = photo_plan[index]
            base = _fit_cover(
                Image.open(photos[entry["index"]]).convert("RGB"),
                (config.video_width, config.video_height),
                entry["centering"],
                entry["zoom"],
            )
            text = _build_editorial_text_layer(content_package, scene, index, config, str(entry["align"]))
            blank = Image.new("RGBA", text.size, (0, 0, 0, 0))
            character, accent = blank, blank.copy()
            scene_background = blank.copy()
        else:
            base = None
            scene_background = background.copy()
            character = _build_character_layer(content_package, config, scene_index=index)
            accent = _build_scene_accent_layer(content_package, index, config)
            text = _build_text_layer(content_package, scene, index, config)

        character_path = render_dir / f"character_{index + 1:02d}.png"
        accent_path = render_dir / f"accent_{index + 1:02d}.png"
        text_path = render_dir / f"text_{index + 1:02d}.png"
        if keep:
            _save_layer(character, character_path)
            _save_layer(accent, accent_path)
            _save_layer(text, text_path)

        _compose_scene(
            [scene_background, accent, character, text],
            (config.video_width, config.video_height),
            slides_dir / f"slide_{index + 1:02d}.png",
            base=base,
        )
        assets.append(
            SceneRenderAssets(
                background_path=background_path,
                text_overlay_path=text_path,
                character_overlay_path=character_path,
                accent_overlay_path=accent_path,
            )
        )

    if not config.keep_render_layers:
        shutil.rmtree(render_dir, ignore_errors=True)

    return assets
