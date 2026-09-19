"""EDITORIAL - paper, serif, hairlines. The "stylish" direction.

A warm paper ground with grain, a masthead and folio like a magazine page,
Noto Serif CJK for the headlines, wide-tracked caps for the small labels, and
the character set into an arch window on a muted field, cropped by its edge.
Restraint does the work here: one accent, lots of air.
"""

from __future__ import annotations

from mbti_tiktok_bot.design import effects as fx
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.core import (
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
)
from mbti_tiktok_bot.design.kit import Layers, arch_mask, blank, canvas, framed

MASTHEAD = "MBTI JOURNAL"


def colors(ctx: Context) -> dict[str, str]:
    accent = fx.mix(ctx.palette.accent_deep, "#8c7b6b", 0.18)
    return {
        "paper": fx.mix("#f3eee5", ctx.palette.light, 0.12),
        "ink": "#1c1a17",
        "muted": "#6d665d",
        "accent": accent,
        "field": fx.mix(ctx.palette.accent, "#efe7da", 0.62),
        "rule": "#1c1a17",
    }


def background(ctx: Context):
    if "editorial.bg" in ctx.cache:
        return ctx.cache["editorial.bg"]
    c = colors(ctx)
    image = fx.solid(ctx.device, fx.rgba(c["paper"]))
    image = fx.grain(image, 0.045, seed=ctx.topic_seed)
    ctx.cache["editorial.bg"] = image
    return image


def _issue(ctx: Context) -> str:
    return f"No.{ctx.topic_seed % 90 + 10:02d}"


def _masthead(draw, ctx: Context, right_label: str) -> float:
    """Title of the 'publication' on the left, folio on the right, a rule under both."""
    c = colors(ctx)
    left = T.single(MASTHEAD, "label", 34, tracking_em=0.32)
    right = T.single(right_label, "label", 34, tracking_em=0.22)
    T.draw(draw, left, SAFE_LEFT, SAFE_TOP, fx.rgba(c["ink"]))
    T.draw(draw, right, SAFE_RIGHT - right.width, SAFE_TOP, fx.rgba(c["ink"]))
    rule_y = SAFE_TOP + T.ink_height(left) + 22
    draw.line((SAFE_LEFT, rule_y, SAFE_RIGHT, rule_y), fill=fx.rgba(c["rule"]), width=2)
    return rule_y


def _title(text: str, width: float, height: float, base: int, minimum: int, lines: int = 3) -> T.Block:
    return T.fit(text, "serif-black", width, height, base, minimum, leading=1.18, tracking_em=0.01,
                 max_lines=lines, strict=True)


def _body(text: str, width: float, height: float = 420, base: int = 42) -> T.Block:
    return T.fit(text, "serif-light", width, height, base, 32, leading=1.85)


def _chips(ctx: Context, slide: Slide) -> list[Chip]:
    c = colors(ctx)
    return [Chip(label, "jp-medium", 28, fill=None, color=fx.rgba(c["ink"]), outline=fx.rgba(c["ink"], 200),
                 tracking_em=0.04, stroke=2) for label in slide.chips]


def _portrait(ctx: Context, box, height_factor: float = 1.08, inset: float = 0.10):
    c = colors(ctx)
    height = (box[3] - box[1]) * height_factor
    return framed(ctx, box, arch_mask(ctx, box), fx.rgba(c["field"]), height, (box[3] - box[1]) * inset)


def cover(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    text = blank(ctx)
    draw = canvas(text, ctx)
    rule_y = _masthead(draw, ctx, _issue(ctx))

    hook = _body(ctx.package.hook, SAFE_WIDTH, 220, 40)
    title = _title(slide.title, SAFE_WIDTH, 360, 112, 64)
    kicker = T.single(f"{ctx.package.mbti_type} — {ctx.package.archetype_name}", "jp-medium", 30, tracking_em=0.12)
    hook_top = SAFE_BOTTOM - hook.height
    title_top = hook_top - 44 - title.height
    kicker_top = title_top - 40 - T.ink_height(kicker)

    arch_box = (SAFE_LEFT + 60, rule_y + 48, SAFE_RIGHT - 60, kicker_top - 48)
    character = _portrait(ctx, arch_box)

    T.draw(draw, kicker, SAFE_LEFT, kicker_top, fx.rgba(c["accent"]))
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    T.draw(draw, hook, SAFE_LEFT, hook_top, fx.rgba(c["muted"]))
    return Layers(bg, blank(ctx), character, text)


def body(ctx: Context, slide: Slide) -> Layers:
    variant = (slide.number - 1) % 3
    return (_body_column, _body_portrait, _body_quote)[variant](ctx, slide)


def _folio(slide: Slide) -> str:
    return f"{slide.number:02d} / {slide.total:02d}"


def _copy(draw, ctx: Context, slide: Slide, left: float, width: float, top: float, base: int = 42,
          draw_it: bool = True) -> float:
    c = colors(ctx)
    chips = _chips(ctx, slide)
    height = chip_flow(draw, chips, left, top, width, draw=draw_it) if chips else 0
    y = top + (height + 30 if chips else 0)
    block = _body(slide.body, width, base=base) if slide.body else None
    if block and draw_it:
        T.draw(draw, block, left, y, fx.rgba(c["ink"], 230))
    return (y - top) + (block.height if block else 0)


def _body_column(ctx: Context, slide: Slide) -> Layers:
    """A big serif numeral, the headline, a text column, a small arch to the side."""
    c = colors(ctx)
    bg = background(ctx).copy()
    text = blank(ctx)
    draw = canvas(text, ctx)
    rule_y = _masthead(draw, ctx, _folio(slide))

    numeral = T.single(f"{slide.number:02d}", "serif-black", 220)
    T.draw(draw, numeral, SAFE_LEFT - 6, rule_y + 60, fx.rgba(c["accent"]))
    title_top = rule_y + 60 + numeral.height + 36
    title = _title(slide.title, SAFE_WIDTH, 320, 100, 60)
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    rule2 = title_top + title.height + 44
    draw.line((SAFE_LEFT, rule2, SAFE_LEFT + 120, rule2), fill=fx.rgba(c["accent"]), width=4)

    column = SAFE_WIDTH * 0.60
    copy_top = rule2 + 44
    _copy(draw, ctx, slide, SAFE_LEFT, column, copy_top, base=40)
    arch_box = (SAFE_LEFT + column + 40, max(copy_top, SAFE_BOTTOM - 520), SAFE_RIGHT + 30, SAFE_BOTTOM)
    character = _portrait(ctx, arch_box, 1.15, 0.08)
    return Layers(bg, blank(ctx), character, text)


def _body_portrait(ctx: Context, slide: Slide) -> Layers:
    """A tall arch on the left with a vertical label; headline and copy below."""
    c = colors(ctx)
    bg = background(ctx).copy()
    text = blank(ctx)
    draw = canvas(text, ctx)
    rule_y = _masthead(draw, ctx, _folio(slide))

    used = _copy(draw, ctx, slide, 0, SAFE_WIDTH, 0, draw_it=False)
    copy_top = SAFE_BOTTOM - used
    title = _title(slide.title, SAFE_WIDTH, 300, 104, 60, lines=2)
    title_top = copy_top - 44 - title.height
    arch_box = (SAFE_LEFT, rule_y + 48, SAFE_LEFT + SAFE_WIDTH * 0.62, title_top - 56)
    character = _portrait(ctx, arch_box)

    side_x = arch_box[2] + 44
    label = T.single(f"POINT {slide.number:02d}", "label", 44, tracking_em=0.24)
    T.draw(draw, label, side_x, arch_box[1] + 20, fx.rgba(c["accent"]))
    numeral = T.single(f"{slide.number:02d}", "serif-black", 150)
    T.draw(draw, numeral, side_x, arch_box[1] + 100, fx.rgba(c["ink"]))
    draw.line((side_x, arch_box[1] + 300, SAFE_RIGHT, arch_box[1] + 300), fill=fx.rgba(c["rule"], 150), width=2)
    type_line = T.fit(f"{ctx.package.mbti_type}\n{ctx.package.archetype_name}", "jp-medium",
                      SAFE_RIGHT - side_x, 160, 30, 22, leading=1.5)
    T.draw(draw, type_line, side_x, arch_box[1] + 336, fx.rgba(c["muted"]))

    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))
    _copy(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, copy_top)
    return Layers(bg, blank(ctx), character, text)


def _body_quote(ctx: Context, slide: Slide) -> Layers:
    """The headline as a pull quote between oversized brackets, a round portrait below."""
    c = colors(ctx)
    bg = background(ctx).copy()
    text = blank(ctx)
    draw = canvas(text, ctx)
    rule_y = _masthead(draw, ctx, _folio(slide))

    open_mark = T.single("「", "serif-black", 220, compress=False)
    T.draw(draw, open_mark, SAFE_LEFT - 30, rule_y + 60, fx.rgba(c["accent"]))
    title = _title(slide.title, SAFE_WIDTH - 60, 420, 124, 64)
    title_top = rule_y + 60 + open_mark.height + 20
    T.draw(draw, title, SAFE_LEFT + 30, title_top, fx.rgba(c["ink"]))
    close_mark = T.single("」", "serif-black", 220, compress=False)
    T.draw(draw, close_mark, SAFE_RIGHT - close_mark.width + 30, title_top + title.height + 10, fx.rgba(c["accent"]))

    used = _copy(draw, ctx, slide, 0, SAFE_WIDTH * 0.58, 0, draw_it=False)
    copy_top = SAFE_BOTTOM - used
    _copy(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH * 0.58, copy_top)
    circle = (SAFE_LEFT + SAFE_WIDTH * 0.64, SAFE_BOTTOM - 320, SAFE_RIGHT + 20, SAFE_BOTTOM)
    size = circle[2] - circle[0]
    circle = (circle[0], circle[3] - size, circle[2], circle[3])
    mask = fx.Image.new("L", ctx.device, 0)
    canvas(mask, ctx).ellipse(circle, fill=255)
    character = framed(ctx, circle, mask, fx.rgba(c["field"]), size * 1.25, size * 0.08)
    return Layers(bg, blank(ctx), character, text)


def closer(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    text = blank(ctx)
    draw = canvas(text, ctx)
    rule_y = _masthead(draw, ctx, "FIN.")

    rows = (("SAVE", "保存して見返す"), ("COMMENT", "当たってたらコメント"), ("SHARE", "友だちと答え合わせ"))
    row_height = 92
    rows_top = SAFE_BOTTOM - row_height * len(rows)
    for i, (en, jp) in enumerate(rows):
        y = rows_top + i * row_height
        draw.line((SAFE_LEFT, y, SAFE_RIGHT, y), fill=fx.rgba(c["rule"], 170), width=2)
        label = T.single(en, "label", 40, tracking_em=0.26)
        T.draw(draw, label, SAFE_LEFT, y + (row_height - T.ink_height(label)) / 2, fx.rgba(c["accent"]))
        words = T.single(jp, "jp-medium", 32, tracking_em=0.06)
        T.draw(draw, words, SAFE_RIGHT - words.width, y + (row_height - T.ink_height(words)) / 2, fx.rgba(c["ink"]))
    title = _title(slide.title, SAFE_WIDTH, 220, 96, 60, lines=2)
    title_top = rows_top - 56 - title.height
    T.draw(draw, title, SAFE_LEFT, title_top, fx.rgba(c["ink"]))

    arch_box = (SAFE_LEFT + 120, rule_y + 48, SAFE_RIGHT - 120, title_top - 56)
    character = _portrait(ctx, arch_box)
    return Layers(bg, blank(ctx), character, text)
