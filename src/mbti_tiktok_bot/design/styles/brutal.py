"""BRUTAL - flat, gridded, oversized. The "cutting edge" direction.

A flat field - bone white, or the accent itself at full strength - with the
construction grid left showing and crop marks in the corners. The MBTI letters
are set so large they run off the canvas, the character sits in front of them
in a hard two-tone, and the Japanese is black, tight and flush left. Labels are
bracketed caps; counters are black boxes.
"""

from __future__ import annotations

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
    vivid,
)
from mbti_tiktok_bot.design.kit import Layers, arrow, blank, canvas, paste, subject
from mbti_tiktok_bot.visuals import _seed_choice

INK = "#0d0d0d"


def colors(ctx: Context) -> dict[str, str]:
    accent = vivid(ctx.palette.accent, 0.86, 0.96)
    loud = _seed_choice(ctx.topic_seed, "brutal.mode", 2) == 1
    return {
        "field": accent if loud else "#ebeae4",
        "accent": "#f4f3ee" if loud else accent,
        "ink": INK,
        "grid": INK,
        "loud": "1" if loud else "",
    }


def background(ctx: Context):
    if "brutal.bg" in ctx.cache:
        return ctx.cache["brutal.bg"]
    c = colors(ctx)
    image = fx.solid(ctx.device, fx.rgba(c["field"]))
    draw = canvas(image, ctx)
    columns = 6
    step = WIDTH / columns
    for i in range(1, columns):
        draw.line((i * step, 0, i * step, HEIGHT), fill=fx.rgba(c["grid"], 26), width=1)
    for y in range(0, HEIGHT, int(step)):
        draw.line((0, y, WIDTH, y), fill=fx.rgba(c["grid"], 16), width=1)
    # Crop marks.
    for x, y, sx, sy in ((28, 28, 1, 1), (WIDTH - 28, 28, -1, 1), (28, HEIGHT - 28, 1, -1), (WIDTH - 28, HEIGHT - 28, -1, -1)):
        draw.line((x, y, x + 44 * sx, y), fill=fx.rgba(c["ink"], 200), width=2)
        draw.line((x, y, x, y + 44 * sy), fill=fx.rgba(c["ink"], 200), width=2)
    image = fx.grain(image, 0.03, seed=ctx.topic_seed)
    ctx.cache["brutal.bg"] = image
    return image


def _treat(ctx: Context):
    c = colors(ctx)
    light = "#ffffff" if c["loud"] else c["accent"]

    def treat(figure):
        toned = fx.duotone(figure, c["ink"], light)
        return fx.shadow(toned, (ctx.px(14), ctx.px(14)), 0.1, fx.rgba(c["ink"], 255))

    return treat


def _mega(layer, ctx: Context, label: str, y: float, size: int = 900, color=None, x: float = -24) -> T.Block:
    c = colors(ctx)
    block = T.single(label, "display", size, tracking_em=-0.02)
    T.draw(canvas(layer, ctx), block, x, y, color or fx.rgba(c["ink"]))
    return block


def _box(draw, x: float, y: float, label: str, size: int = 44, role: str = "label", fill=INK, color="#ffffff") -> tuple[float, float]:
    chip = Chip(label, role, size, fill=fx.rgba(fill), color=fx.rgba(color), tracking_em=0.12, pad_x=0.55,
                height_em=1.7)
    draw.rectangle((x, y, x + chip.width, y + chip.height), fill=fx.rgba(fill))
    block = chip.block
    T.draw(draw, block, x + chip.size * chip.pad_x, y + (chip.height - T.ink_height(block)) / 2, fx.rgba(color))
    return chip.width, chip.height


def _tag(draw, ctx: Context, x: float, y: float) -> float:
    c = colors(ctx)
    label = T.single(f"[{ctx.package.mbti_type}]  {ctx.package.archetype_name}", "jp-bold", 30, tracking_em=0.08)
    T.draw(draw, label, x, y, fx.rgba(c["ink"]))
    return T.ink_height(label)


def _title(text: str, width: float, height: float, base: int, minimum: int, lines: int = 3) -> T.Block:
    return T.fit(text, "jp-black", width, height, base, minimum, leading=1.02, tracking_em=-0.05,
                 max_lines=lines, strict=True)


def _copy(draw, ctx: Context, slide: Slide, left: float, width: float, top: float, draw_it: bool = True) -> float:
    """A thick rule, then chips and the body in a narrow column. Returns the height used."""
    c = colors(ctx)
    if draw_it:
        draw.rectangle((left, top, left + 120, top + 12), fill=fx.rgba(c["ink"]))
    y = top + 44
    chips = [Chip(label, "jp-bold", 28, fill=None, color=fx.rgba(c["ink"]), outline=fx.rgba(c["ink"]),
                  tracking_em=0.02, stroke=3) for label in slide.chips]
    if chips:
        y += chip_flow(draw, chips, left, y, width, draw=draw_it) + 26
    block = T.fit(slide.body, "jp-medium", width, 480, 44, 32, leading=1.6) if slide.body else None
    if block and draw_it:
        T.draw(draw, block, left, y, fx.rgba(c["ink"]))
    return (y - top) + (block.height if block else 0)


def _barcode(draw, ctx: Context, x: float, y: float, height: float = 70) -> None:
    c = colors(ctx)
    rng = random.Random(ctx.topic_seed)
    pen = x
    for _ in range(26):
        w = rng.choice((2, 2, 4, 6))
        draw.rectangle((pen, y, pen + w, y + height), fill=fx.rgba(c["ink"]))
        pen += w + rng.choice((3, 4, 6))


def cover(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    mega_color = fx.rgba(c["accent"] if not c["loud"] else c["ink"])
    _mega(accent, ctx, ctx.package.mbti_type, 980, 760, mega_color)

    character = blank(ctx)
    treated, size = subject(ctx, 1260, _treat(ctx), max_width=960)
    paste(character, ctx, treated, size, (WIDTH * 0.62, 1780))

    text = blank(ctx)
    draw = canvas(text, ctx)
    _tag(draw, ctx, SAFE_LEFT, SAFE_TOP)
    _, box_h = _box(draw, SAFE_RIGHT - 150, SAFE_TOP - 10, "FILE 00")
    title = _title(slide.title, SAFE_WIDTH, 460, 150, 72)
    title_top = SAFE_TOP + box_h + 60
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    hook = T.fit(ctx.package.hook, "jp-bold", SAFE_WIDTH * 0.66, 300, 36, 28, leading=1.55, max_lines=5)
    hook_top = title_top + title.height + 44
    draw.rectangle((SAFE_LEFT, hook_top, SAFE_LEFT + hook.width + 48, hook_top + hook.height + 48), fill=fx.rgba(c["ink"]))
    T.draw(draw, hook, SAFE_LEFT + 24, hook_top + 24, (255, 255, 255, 255))
    arrow(draw, SAFE_RIGHT - 110, SAFE_BOTTOM - 20, 110, fx.rgba(c["ink"]), width=8)
    swipe = T.single("SWIPE", "label", 44, tracking_em=0.2)
    T.draw(draw, swipe, SAFE_RIGHT - 110 - 24 - swipe.width, SAFE_BOTTOM - 20 - T.ink_height(swipe) / 2, fx.rgba(c["ink"]))
    return Layers(bg, accent, character, text)


def body(ctx: Context, slide: Slide) -> Layers:
    variant = (slide.number - 1) % 3
    return (_body_file, _body_mega, _body_split)[variant](ctx, slide)


def _body_file(ctx: Context, slide: Slide) -> Layers:
    """A numbered file card: box, headline, ruled column, character in the corner."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)

    number = T.single(f"{slide.number:02d}", "display", 200)
    draw.rectangle((SAFE_LEFT, SAFE_TOP, SAFE_LEFT + number.width + 60, SAFE_TOP + number.height + 60), fill=fx.rgba(c["ink"]))
    T.draw(draw, number, SAFE_LEFT + 30, SAFE_TOP + 30, fx.rgba(c["field"]))
    label = T.single(f"/{slide.total:02d}", "label", 60, tracking_em=0.04)
    T.draw(draw, label, SAFE_LEFT + number.width + 84, SAFE_TOP + number.height + 30 - T.ink_height(label), fx.rgba(c["ink"]))
    _tag(draw, ctx, SAFE_LEFT + number.width + 84, SAFE_TOP + 30)

    title_top = SAFE_TOP + number.height + 60 + 56
    title = _title(slide.title, SAFE_WIDTH, 360, 132, 64)
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    column = SAFE_WIDTH * 0.58
    copy_top = title_top + title.height + 60
    _copy(draw, ctx, slide, SAFE_LEFT, column, copy_top)

    character = blank(ctx)
    treated, size = subject(ctx, 880, _treat(ctx), max_width=620)
    paste(character, ctx, treated, size, (WIDTH * 0.80, 1820))
    _barcode(draw, ctx, SAFE_LEFT, SAFE_BOTTOM - 70)
    return Layers(bg, accent, character, text)


def _body_mega(ctx: Context, slide: Slide) -> Layers:
    """The number set enormous behind the character; the headline on a black band."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    mega_color = fx.rgba(c["accent"] if not c["loud"] else c["ink"], 255)
    _mega(accent, ctx, f"{slide.number:02d}", SAFE_TOP - 40, 1040, mega_color, x=-40)

    text = blank(ctx)
    draw = canvas(text, ctx)
    used = _copy(draw, ctx, slide, 0, SAFE_WIDTH, 0, draw_it=False)
    copy_top = SAFE_BOTTOM - used
    title = _title(slide.title, SAFE_WIDTH - 48, 300, 116, 60, lines=2)
    band_bottom = copy_top - 48
    band_top = band_bottom - title.height - 64
    character = blank(ctx)
    room = band_top - (SAFE_TOP + 40)
    treated, size = subject(ctx, max(min(room + 120, 1100), 460), _treat(ctx), max_width=900)
    paste(character, ctx, treated, size, (WIDTH * 0.58, band_top + 120))

    draw.rectangle((0, band_top, WIDTH, band_bottom), fill=fx.rgba(c["ink"]))
    T.draw(draw, title, SAFE_LEFT, band_top + 32, (255, 255, 255, 255))
    _box(draw, SAFE_RIGHT - 170, band_top - 70, f"{slide.number:02d}/{slide.total:02d}", fill=c["field"], color=c["ink"])
    _copy(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, copy_top)
    return Layers(bg, accent, character, text)


def _body_split(ctx: Context, slide: Slide) -> Layers:
    """A hard split: the character on a block of colour above, the copy on the field below."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)

    used = _copy(draw, ctx, slide, 0, SAFE_WIDTH, 0, draw_it=False)
    copy_top = SAFE_BOTTOM - used
    title = _title(slide.title, SAFE_WIDTH, 320, 124, 60, lines=3)
    title_top = copy_top - 56 - title.height
    split = title_top - 64
    block_color = c["ink"] if not c["loud"] else "#f4f3ee"
    canvas(accent, ctx).rectangle((0, 0, WIDTH, split), fill=fx.rgba(block_color))
    tag = T.single(f"FILE {slide.number:02d} / {slide.total:02d}", "label", 44, tracking_em=0.18)
    T.draw(canvas(accent, ctx), tag, SAFE_LEFT, SAFE_TOP, fx.rgba(c["field"] if not c["loud"] else c["ink"]))

    character = blank(ctx)
    room = split - (SAFE_TOP + 90)
    treated, size = subject(ctx, max(min(room + 80, 1080), 420), _treat(ctx), max_width=900)
    paste(character, ctx, treated, size, (WIDTH * 0.52, split + 80))
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    _copy(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, copy_top)
    return Layers(bg, accent, character, text)


def closer(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    mega_color = fx.rgba(c["accent"] if not c["loud"] else c["ink"])
    _mega(accent, ctx, ctx.package.mbti_type, 200, 760, mega_color)

    text = blank(ctx)
    draw = canvas(text, ctx)
    actions = ("保存する", "コメント", "シェア")
    widths = []
    for label in actions:
        chip = Chip(label, "jp-black", 34, fill=fx.rgba(c["ink"]), color=(255, 255, 255, 255), pad_x=0.8, height_em=1.9)
        widths.append(chip)
    _, row_height = chip_row(draw, widths, 0, 0, SAFE_WIDTH, gap=16, draw=False)
    actions_top = SAFE_BOTTOM - row_height
    body_block = T.fit(slide.body, "jp-bold", SAFE_WIDTH, 200, 40, 30, leading=1.55)
    body_top = actions_top - 40 - body_block.height
    title = _title(slide.title, SAFE_WIDTH, 260, 124, 64, lines=2)
    title_top = body_top - 40 - title.height

    character = blank(ctx)
    room = title_top - 40 - (SAFE_TOP + 60)
    treated, size = subject(ctx, max(min(room + 60, 1000), 440), _treat(ctx), max_width=880)
    paste(character, ctx, treated, size, (WIDTH / 2, title_top - 20))

    _tag(draw, ctx, SAFE_LEFT, SAFE_TOP)
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    T.draw(draw, body_block, SAFE_LEFT, body_top, fx.rgba(c["ink"]))
    pen = SAFE_LEFT
    for chip in widths:
        draw.rectangle((pen, actions_top, pen + chip.width, actions_top + chip.height), fill=fx.rgba(c["ink"]))
        T.draw(draw, chip.block, pen + chip.size * chip.pad_x, actions_top + (chip.height - T.ink_height(chip.block)) / 2,
               (255, 255, 255, 255))
        pen += chip.width + 16
    return Layers(bg, accent, character, text)
