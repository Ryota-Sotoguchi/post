"""BUBBLE - pastel, round, sticker-like. The "cute" direction.

A pale wash of the palette with polka dots and sparkles, the character cut out
as a sticker with a thick white border on a big coloured disc, headlines set
as sticker type - dark ink with a white outline and a soft coloured drop.
Copy sits on white cards with generous corners, or in a speech bubble.
"""

from __future__ import annotations

import math
import random

from mbti_tiktok_bot.design import effects as fx
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.core import (
    HEIGHT,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    SAFE_WIDTH,
    WIDTH,
    Chip,
    Context,
    Slide,
    chip_flow,
    chip_row,
    neon_partner,
    vivid,
)
from mbti_tiktok_bot.design.kit import Layers, blank, canvas, paste, subject, swipe_cue

WHITE = (255, 255, 255, 255)


def colors(ctx: Context) -> dict[str, str]:
    base = vivid(ctx.palette.accent, 0.62, 0.96)
    partner = neon_partner(base)
    return {
        "paper": fx.mix(base, "#ffffff", 0.84),
        "pastel": fx.mix(base, "#ffffff", 0.50),
        "pastel2": fx.mix(partner, "#ffffff", 0.58),
        "pop": vivid(ctx.palette.accent, 0.66, 0.92),
        "pop2": vivid(partner, 0.55, 0.98),
        "ink": fx.mix(ctx.palette.accent_deep, "#140c1c", 0.45),
    }


def _sparkle(draw, cx: float, cy: float, r: float, color) -> None:
    """A four-pointed twinkle."""
    waist = r * 0.28
    draw.polygon([(cx, cy - r), (cx + waist, cy - waist), (cx + r, cy), (cx + waist, cy + waist),
                  (cx, cy + r), (cx - waist, cy + waist), (cx - r, cy), (cx - waist, cy - waist)], fill=color)


def background(ctx: Context):
    if "bubble.bg" in ctx.cache:
        return ctx.cache["bubble.bg"]
    c = colors(ctx)
    w, h = ctx.device
    s = ctx.scale
    image = fx.aurora(
        ctx.device,
        fx.rgba(c["paper"]),
        [
            ((w * 0.10, h * 0.12), 620 * s, fx.rgba(c["pastel2"], 170)),
            ((w * 0.95, h * 0.55), 700 * s, fx.rgba(c["pastel"], 150)),
            ((w * 0.20, h * 0.95), 560 * s, fx.rgba(c["pastel2"], 120)),
        ],
    )
    draw = canvas(image, ctx)
    # Polka dots on a slanted lattice, sparkles scattered by the topic seed.
    for row, gy in enumerate(range(40, HEIGHT + 60, 88)):
        for gx in range(-40 + (row % 2) * 44, WIDTH + 60, 88):
            draw.ellipse((gx - 7, gy - 7, gx + 7, gy + 7), fill=(255, 255, 255, 120))
    rng = random.Random(ctx.topic_seed)
    for _ in range(14):
        x, y = rng.uniform(40, WIDTH - 40), rng.uniform(80, HEIGHT - 80)
        _sparkle(draw, x, y, rng.uniform(10, 26), fx.rgba(rng.choice([c["pop"], c["pop2"], "#ffffff"]), 200))
    image = fx.grain(image, 0.025, seed=ctx.topic_seed)
    ctx.cache["bubble.bg"] = image
    return image


def _treat(ctx: Context, tilt: float = 0.0):
    c = colors(ctx)

    def treat(figure):
        sticker = fx.outline(figure, ctx.px(12), (255, 255, 255, 255))
        if tilt:
            sticker = sticker.rotate(tilt, resample=fx.Image.Resampling.BICUBIC, expand=True)
        return fx.shadow(sticker, (ctx.px(6), ctx.px(14)), ctx.px(10), fx.rgba(c["ink"], 70))

    return treat


def _tilt(ctx: Context, slide: Slide) -> float:
    return (-5, 3, -2, 5, -4, 2)[(ctx.topic_seed // 5 + slide.index) % 6]


def _disc(layer, ctx: Context, cx: float, cy: float, r: float, color: str) -> None:
    draw = canvas(layer, ctx)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fx.rgba(color))
    # A second, offset ring gives the disc a hand-cut look.
    draw.ellipse((cx - r + 18, cy - r - 10, cx + r + 18, cy + r - 10), outline=(255, 255, 255, 190), width=5)


def _sticker_title(draw, block: T.Block, x: float, y: float, c: dict, align: str = "left", width: float | None = None) -> None:
    T.draw(draw, block, x, y, fx.rgba(c["ink"]), align=align, box_width=width,
           stroke=max(block.size // 9, 5), stroke_fill=WHITE, shadow=(0, block.size * 0.08, fx.rgba(c["pop"], 170)))


def _title(text: str, width: float, height: float, base: int, minimum: int, lines: int = 3) -> T.Block:
    return T.fit(text, "jp-black", width, height, base, minimum, leading=1.12, tracking_em=0.0,
                 max_lines=lines, strict=True)


def _top_row(layer, ctx: Context, cue: str = "SWIPE") -> float:
    c = colors(ctx)
    draw = canvas(layer, ctx)
    package = ctx.package
    chip = Chip(f"{package.mbti_type}・{package.archetype_name}", "jp-bold", 30,
                fill=fx.rgba(c["ink"]), color=WHITE, tracking_em=0.04)
    _, height = chip_row(draw, [chip], SAFE_LEFT, SAFE_TOP, SAFE_WIDTH - 220)
    cue_height = T.ink_height(T.single(cue, "label", 40))
    swipe_cue(draw, SAFE_RIGHT, SAFE_TOP + (height - cue_height) / 2, fx.rgba(c["ink"]), cue, size=40)
    return height


def _card(layer, ctx: Context, box, radius: float = 48) -> None:
    c = colors(ctx)
    shadow = blank(ctx)
    canvas(shadow, ctx).rounded_rectangle((box[0] + 4, box[1] + 18, box[2] + 4, box[3] + 18), radius=radius,
                                          fill=fx.rgba(c["pop"], 70))
    layer.alpha_composite(shadow.filter(fx.ImageFilter.GaussianBlur(ctx.px(14))))
    canvas(layer, ctx).rounded_rectangle(box, radius=radius, fill=(255, 255, 255, 246))


def _chips(ctx: Context, slide: Slide) -> list[Chip]:
    c = colors(ctx)
    fills = (c["pastel"], c["pastel2"])
    return [Chip(label, "jp-bold", 30, fill=fx.rgba(fills[i % 2]), color=fx.rgba(c["ink"]), tracking_em=0.02)
            for i, label in enumerate(slide.chips)]


def _copy(draw, ctx: Context, slide: Slide, left: float, width: float, top: float, draw_it: bool = True) -> float:
    """Chips then body, top-aligned. Returns the height used."""
    c = colors(ctx)
    chips = _chips(ctx, slide)
    chip_height = chip_flow(draw, chips, left, top, width, draw=draw_it) if chips else 0
    y = top + (chip_height + 28 if chips else 0)
    block = T.fit(slide.body, "jp-medium", width, 480, 46, 34, leading=1.62) if slide.body else None
    if block and draw_it:
        T.draw(draw, block, left, y, fx.rgba(c["ink"], 235))
    return (y - top) + (block.height if block else 0)


def cover(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)
    row = _top_row(text, ctx)

    inner = SAFE_WIDTH - 96
    hook = T.fit(ctx.package.hook, "jp-bold", inner, 260, 42, 30, leading=1.55, max_lines=4)
    title = _title(slide.title, SAFE_WIDTH, 400, 118, 64)
    card_bottom = SAFE_BOTTOM
    card_top = card_bottom - hook.height - 96
    title_top = card_top - 48 - title.height

    room = title_top - 40 - (SAFE_TOP + row + 30)
    disc_r = min(room / 2 + 40, 440)
    disc_cy = SAFE_TOP + row + 30 + room / 2
    _disc(accent, ctx, WIDTH / 2, disc_cy, disc_r, c["pastel"])
    character = blank(ctx)
    treated, size = subject(ctx, max(room + 60, 480), _treat(ctx, _tilt(ctx, slide)), max_width=880)
    paste(character, ctx, treated, size, (WIDTH / 2, title_top - 10))

    _card(accent, ctx, (SAFE_LEFT - 16, card_top, SAFE_RIGHT + 16, card_bottom))
    _sticker_title(draw, title, SAFE_LEFT, title_top, c, align="center", width=SAFE_WIDTH)
    T.draw(draw, hook, SAFE_LEFT + 32, card_top + 48, fx.rgba(c["ink"]), align="center", box_width=inner + 32)
    return Layers(bg, accent, character, text)


def body(ctx: Context, slide: Slide) -> Layers:
    variant = (slide.number - 1) % 3
    return (_body_card, _body_speech, _body_hero)[variant](ctx, slide)


def _badge(draw, ctx: Context, slide: Slide, x: float, y: float, r: float = 76) -> None:
    c = colors(ctx)
    draw.ellipse((x, y, x + r * 2, y + r * 2), fill=fx.rgba(c["pop"]))
    number = T.single(f"{slide.number:02d}", "display", int(r * 0.95))
    T.draw(draw, number, x, y + r - T.ink_height(number) / 2, WHITE, align="center", box_width=r * 2)


def _body_card(ctx: Context, slide: Slide) -> Layers:
    """Numbered badge and sticker headline, copy on a white card, character peeking below."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)

    _badge(draw, ctx, slide, SAFE_LEFT, SAFE_TOP)
    total = T.single(f"/ {slide.total:02d}", "label", 44, tracking_em=0.08)
    T.draw(draw, total, SAFE_LEFT + 172, SAFE_TOP + 76 - T.ink_height(total) / 2, fx.rgba(c["ink"], 160))
    title_top = SAFE_TOP + 152 + 40
    title = _title(slide.title, SAFE_WIDTH, 330, 112, 60)
    _sticker_title(draw, title, SAFE_LEFT, title_top, c)

    card_left, card_right = SAFE_LEFT - 16, SAFE_RIGHT + 16
    inner = card_right - card_left - 96
    card_top = title_top + title.height + 56
    used = _copy(draw, ctx, slide, 0, inner, 0, draw_it=False)
    card_bottom = card_top + used + 96
    _card(accent, ctx, (card_left, card_top, card_right, card_bottom))
    _copy(draw, ctx, slide, card_left + 48, inner, card_top + 48)

    character = blank(ctx)
    room = SAFE_BOTTOM + 260 - (card_bottom + 20)
    treated, size = subject(ctx, max(min(room, 720), 380), _treat(ctx, _tilt(ctx, slide)), max_width=560)
    paste(character, ctx, treated, size, (WIDTH * 0.70, max(card_bottom + 20 + min(room, 720), SAFE_BOTTOM + 120)))
    return Layers(bg, accent, character, text, order=("background", "character", "accent", "text"))


def _speech_bubble(layer, ctx: Context, box, tail_x: float, tail_down: bool = True) -> None:
    c = colors(ctx)
    left, top, right, bottom = box
    shadow = blank(ctx)
    sd = canvas(shadow, ctx)
    sd.rounded_rectangle((left + 6, top + 18, right + 6, bottom + 18), radius=64, fill=fx.rgba(c["pop2"], 90))
    layer.alpha_composite(shadow.filter(fx.ImageFilter.GaussianBlur(ctx.px(12))))
    draw = canvas(layer, ctx)
    draw.rounded_rectangle(box, radius=64, fill=(255, 255, 255, 250))
    if tail_down:
        draw.polygon([(tail_x - 40, bottom - 4), (tail_x + 40, bottom - 4), (tail_x - 10, bottom + 70)], fill=(255, 255, 255, 250))


def _body_speech(ctx: Context, slide: Slide) -> Layers:
    """The character talking: copy in a speech bubble with its tail on the character."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)

    counter = Chip(f"{slide.number:02d} / {slide.total:02d}", "label", 40, fill=fx.rgba(c["pop"]), color=WHITE,
                   tracking_em=0.1, pad_x=0.8)
    _, counter_height = chip_row(draw, [counter], SAFE_LEFT, SAFE_TOP, SAFE_WIDTH)

    left, right = SAFE_LEFT - 16, SAFE_RIGHT + 16
    inner = right - left - 104
    title = _title(slide.title, inner, 300, 100, 56, lines=3)
    top = SAFE_TOP + counter_height + 36
    used = _copy(draw, ctx, slide, 0, inner, 0, draw_it=False)
    bottom = top + 52 + title.height + 36 + used + 60
    _speech_bubble(accent, ctx, (left, top, right, bottom), tail_x=WIDTH * 0.36)
    T.draw(draw, title, left + 52, top + 52, fx.rgba(c["ink"]))
    _copy(draw, ctx, slide, left + 52, inner, top + 52 + title.height + 36)

    _disc(accent, ctx, WIDTH * 0.34, (bottom + 70 + SAFE_BOTTOM + 200) / 2, 300, c["pastel2"])
    character = blank(ctx)
    room = SAFE_BOTTOM + 220 - (bottom + 80)
    treated, size = subject(ctx, max(min(room, 860), 420), _treat(ctx, _tilt(ctx, slide)), max_width=640)
    paste(character, ctx, treated, size, (WIDTH * 0.34, bottom + 80 + max(min(room, 860), 420)))
    return Layers(bg, accent, character, text)


def _body_hero(ctx: Context, slide: Slide) -> Layers:
    """The character big on its disc; the headline and copy below."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)

    inner = SAFE_WIDTH - 96
    used = _copy(draw, ctx, slide, 0, inner, 0, draw_it=False)
    card_bottom = SAFE_BOTTOM
    card_top = card_bottom - used - 96
    title = _title(slide.title, SAFE_WIDTH, 300, 108, 60, lines=2)
    title_top = card_top - 40 - title.height

    counter = T.single(f"{slide.number:02d} / {slide.total:02d}", "label", 44, tracking_em=0.12)
    T.draw(draw, counter, SAFE_LEFT, SAFE_TOP, fx.rgba(c["ink"], 200))
    room = title_top - 30 - (SAFE_TOP + 70)
    _disc(accent, ctx, WIDTH / 2, SAFE_TOP + 70 + room / 2, min(room / 2 + 30, 430), c["pastel"])
    character = blank(ctx)
    treated, size = subject(ctx, max(room, 420), _treat(ctx, _tilt(ctx, slide)), max_width=860)
    paste(character, ctx, treated, size, (WIDTH / 2, title_top - 20))

    _card(accent, ctx, (SAFE_LEFT - 16, card_top, SAFE_RIGHT + 16, card_bottom))
    _sticker_title(draw, title, SAFE_LEFT, title_top, c, align="center", width=SAFE_WIDTH)
    _copy(draw, ctx, slide, SAFE_LEFT + 32, inner, card_top + 48)
    return Layers(bg, accent, character, text)


def closer(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)
    row = _top_row(text, ctx, "LAST")

    title = _title(slide.title, SAFE_WIDTH, 260, 108, 60, lines=2)
    body_block = T.fit(slide.body, "jp-bold", SAFE_WIDTH - 96, 220, 40, 30, leading=1.55)
    actions = [Chip(label, "jp-black", 32, fill=fx.rgba(fill), color=WHITE, pad_x=1.1)
               for label, fill in (("保存する", c["pop"]), ("コメント", c["pop2"]), ("シェア", c["ink"]))]
    _, actions_height = chip_row(draw, actions, 0, 0, SAFE_WIDTH, gap=16, draw=False)
    actions_top = SAFE_BOTTOM - actions_height
    card_bottom = actions_top - 36
    card_top = card_bottom - body_block.height - 88
    title_top = card_top - 40 - title.height

    room = title_top - 30 - (SAFE_TOP + row + 30)
    _disc(accent, ctx, WIDTH / 2, SAFE_TOP + row + 30 + room / 2, min(room / 2 + 30, 420), c["pastel2"])
    character = blank(ctx)
    treated, size = subject(ctx, max(room, 420), _treat(ctx, _tilt(ctx, slide)), max_width=860)
    paste(character, ctx, treated, size, (WIDTH / 2, title_top - 16))

    _card(accent, ctx, (SAFE_LEFT - 16, card_top, SAFE_RIGHT + 16, card_bottom))
    _sticker_title(draw, title, SAFE_LEFT, title_top, c, align="center", width=SAFE_WIDTH)
    T.draw(draw, body_block, SAFE_LEFT + 48, card_top + 44, fx.rgba(c["ink"]), align="center", box_width=SAFE_WIDTH - 96)
    chip_row(draw, actions, SAFE_LEFT, actions_top, SAFE_WIDTH, gap=16, align="center")
    return Layers(bg, accent, character, text)
